from __future__ import annotations

import csv
import json
from datetime import date, time
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from django.db import transaction
from django.utils import timezone

from costs.models import CostCategoryModel, CostModel
from farms.services.data_backup import BackupImportError, user_business_data_counts
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.actions.inventory import InventoryActions
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import (
    MortalityReportModel,
    PigletTransferModel,
    SowEventModel,
    SowModel,
    VaccinationCycleModel,
    VaccinationPlanModel,
)


MAX_CSV_ARCHIVE_SIZE = 25 * 1024 * 1024

SCHEMAS = {
    "sows.csv": ("id", "ear_tag", "entry_date", "is_archived", "archived_at"),
    "sow_events.csv": ("id", "sow_id", "event_type", "event_date", "details", "vaccination_plan_id", "vaccine_name", "cycle_id", "scheduled_date"),
    "vaccination_plans.csv": ("id", "name", "days_before_farrowing", "days_after_event", "event_source", "interval_months", "interval_value", "interval_unit", "schedule_mode", "first_due_date", "scope", "is_active", "requires_configuration", "selected_sow_ids", "excluded_sow_ids", "reminder_days_ahead"),
    "vaccination_cycles.csv": ("id", "plan_id", "sow_id", "cycle_id", "scheduled_date", "status", "completed_at", "skipped_at", "note"),
    "piglet_transfers.csv": ("id", "source_farrowing_id", "target_farrowing_id", "quantity", "transfer_date", "note", "canceled_at", "cancellation_note"),
    "mortality.csv": ("id", "mortality_type", "sow_id", "farrowing_id", "mortality_date", "quantity", "reason", "note", "source"),
    "ingredients.csv": ("id", "name", "description", "low_stock_threshold_kg", "is_in_bin"),
    "deliveries.csv": ("id", "ingredient_id", "date", "quantity_kg", "price_per_kg"),
    "recipes.csv": ("id", "name"),
    "recipe_items.csv": ("id", "recipe_id", "ingredient_id", "percentage"),
    "productions.csv": ("id", "recipe_id", "date", "time", "quantity_kg", "custom_recipe_data", "status", "completed_at"),
    "sales.csv": ("id", "sale_date", "document_number", "tattoo", "no_settlement", "quantity", "total_weight", "meat_class", "price_per_kg", "avg_meatiness_seurop", "live_weight", "dressing_percentage", "net_value", "vat_value", "gross_value"),
    "sale_rows.csv": ("id", "sale_id", "line_no", "meat_class", "quantity", "weight", "avg_weight", "avg_meatiness", "price_per_kg", "net_value", "vat_value", "gross_value"),
    "cost_categories.csv": ("id", "name", "description", "is_active"),
    "costs.csv": ("id", "category_id", "production_id", "date", "amount", "description", "document_number", "supplier", "is_paid"),
}

OPTIONAL_COLUMNS = {
    "costs.csv": {"production_id"},
    "sow_events.csv": {"vaccination_plan_id", "vaccine_name", "cycle_id", "scheduled_date"},
    "vaccination_plans.csv": {
        "interval_value", "interval_unit", "schedule_mode", "first_due_date", "scope",
        "is_active", "requires_configuration", "selected_sow_ids", "excluded_sow_ids",
    },
    "mortality.csv": {"farrowing_id"},
}
OPTIONAL_FILES = {"vaccination_cycles.csv", "piglet_transfers.csv", "mortality.csv"}


def _value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _write_csv(columns, rows):
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _value(row.get(column)) for column in columns})
    return output.getvalue().encode("utf-8-sig")


def build_csv_export(farm, *, year=None) -> tuple[bytes, str]:
    selected_year = year or timezone.localdate().year
    from sows.selectors.mortality import pre_weaning_mortality_cycles
    datasets = {
        "sows.csv": [
            {"id": obj.pk, "ear_tag": obj.ear_tag, "entry_date": obj.entry_date, "is_archived": obj.is_archived, "archived_at": obj.archived_at}
            for obj in SowModel.objects.filter(farm=farm).order_by("id")
        ],
        "sow_events.csv": [
            {
                "id": obj.pk,
                "sow_id": obj.sow_id,
                "event_type": obj.event_type,
                "event_date": obj.event_date,
                "details": obj.details,
                "vaccination_plan_id": obj.vaccination_plan_id,
                "vaccine_name": obj.vaccine_name,
                "cycle_id": obj.cycle_id,
                "scheduled_date": obj.scheduled_date,
            }
            for obj in SowEventModel.objects.filter(sow__farm=farm).order_by("id")
        ],
        "vaccination_plans.csv": [
            {
                **{
                    column: getattr(obj, column)
                    for column in SCHEMAS["vaccination_plans.csv"]
                    if column not in {"selected_sow_ids", "excluded_sow_ids"}
                },
                "selected_sow_ids": [sow.id for sow in obj.selected_sows.all()],
                "excluded_sow_ids": [sow.id for sow in obj.excluded_sows.all()],
            }
            for obj in VaccinationPlanModel.objects.filter(farm=farm)
            .prefetch_related("selected_sows", "excluded_sows")
            .order_by("id")
        ],
        "vaccination_cycles.csv": [
            {
                "id": obj.pk,
                "plan_id": obj.plan_id,
                "sow_id": obj.sow_id,
                "cycle_id": obj.cycle_id,
                "scheduled_date": obj.scheduled_date,
                "status": obj.status,
                "completed_at": obj.completed_at,
                "skipped_at": obj.skipped_at,
                "note": obj.note,
            }
            for obj in VaccinationCycleModel.objects.filter(plan__farm=farm).order_by("id")
        ],
        "piglet_transfers.csv": [
            {
                "id": obj.pk,
                "source_farrowing_id": obj.source_farrowing_id,
                "target_farrowing_id": obj.target_farrowing_id,
                "quantity": obj.quantity,
                "transfer_date": obj.transfer_date,
                "note": obj.note,
                "canceled_at": obj.canceled_at,
                "cancellation_note": obj.cancellation_note,
            }
            for obj in PigletTransferModel.objects.filter(farm=farm).order_by("id")
        ],
        "mortality.csv": [
            {
                "id": obj.pk,
                "mortality_type": obj.mortality_type,
                "sow_id": obj.sow_id,
                "farrowing_id": obj.farrowing_id,
                "mortality_date": obj.mortality_date,
                "quantity": obj.quantity,
                "reason": obj.reason,
                "note": obj.note,
                "source": "manual",
            }
            for obj in MortalityReportModel.objects.filter(farm=farm).order_by("id")
        ] + [
            {
                "id": f"AUTO-{row.farrowing.id}",
                "mortality_type": "PRZED_ODSADZENIEM",
                "sow_id": row.sow.id,
                "farrowing_id": row.farrowing.id,
                "mortality_date": row.mortality_date,
                "quantity": row.quantity if row.quantity is not None else "",
                "reason": "Wyliczone automatycznie z oproszenia i odsadzenia",
                "note": row.unavailable_reason,
                "source": "automatic",
            }
            for row in pre_weaning_mortality_cycles(farm)
        ],
        "ingredients.csv": [
            {"id": obj.pk, "name": obj.name, "description": obj.description, "low_stock_threshold_kg": obj.low_stock_threshold_kg, "is_in_bin": obj.is_in_bin}
            for obj in IngredientModel.objects.filter(farm=farm).order_by("id")
        ],
        "deliveries.csv": list(DeliveryModel.objects.filter(ingredient__farm=farm).order_by("id").values(*SCHEMAS["deliveries.csv"])),
        "recipes.csv": list(RecipeModel.objects.filter(farm=farm).order_by("id").values(*SCHEMAS["recipes.csv"])),
        "recipe_items.csv": list(RecipeItemModel.objects.filter(recipe__farm=farm).order_by("id").values(*SCHEMAS["recipe_items.csv"])),
        "productions.csv": list(ProductionModel.objects.filter(recipe__farm=farm).order_by("id").values(*SCHEMAS["productions.csv"])),
        "sales.csv": list(PigSaleModel.objects.filter(farm=farm).order_by("id").values(*SCHEMAS["sales.csv"])),
        "sale_rows.csv": list(SaleClassRowModel.objects.filter(sale__farm=farm).order_by("id").values(*SCHEMAS["sale_rows.csv"])),
        "cost_categories.csv": list(CostCategoryModel.objects.filter(farm=farm).order_by("id").values(*SCHEMAS["cost_categories.csv"])),
        "costs.csv": list(CostModel.objects.filter(farm=farm, date__year=selected_year).order_by("id").values(*SCHEMAS["costs.csv"])),
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for filename, columns in SCHEMAS.items():
            archive.writestr(filename, _write_csv(columns, datasets[filename]))
    return buffer.getvalue(), f"eksport_csv_{selected_year}_{timezone.now():%Y-%m-%d_%H-%M-%S}.zip"


def _read_archive(uploaded_file):
    if getattr(uploaded_file, "size", 0) > MAX_CSV_ARCHIVE_SIZE:
        raise BackupImportError("Archiwum CSV jest zbyt duże.")
    try:
        with ZipFile(uploaded_file) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            names = {info.filename for info in infos}
            if len(names) != len(infos):
                raise BackupImportError("Archiwum zawiera zduplikowane nazwy plików.")
            if sum(info.file_size for info in infos) > 100 * 1024 * 1024:
                raise BackupImportError("Rozpakowane archiwum CSV jest zbyt duże.")
            missing = set(SCHEMAS) - OPTIONAL_FILES - names
            if missing:
                raise BackupImportError(f"Brak wymaganych plików: {', '.join(sorted(missing))}.")
            result = {}
            for filename, required in SCHEMAS.items():
                if filename not in names and filename in OPTIONAL_FILES:
                    result[filename] = []
                    continue
                try:
                    text = archive.read(filename).decode("utf-8-sig")
                except UnicodeDecodeError as error:
                    raise BackupImportError(f"Plik {filename} nie jest zapisany w UTF-8.") from error
                reader = csv.DictReader(StringIO(text))
                columns = tuple(reader.fieldnames or ())
                missing_columns = set(required) - OPTIONAL_COLUMNS.get(filename, set()) - set(columns)
                if missing_columns:
                    raise BackupImportError(f"Plik {filename} nie ma kolumn: {', '.join(sorted(missing_columns))}.")
                rows = list(reader)
                ids = [row["id"] for row in rows]
                if any(not item for item in ids) or len(ids) != len(set(ids)):
                    raise BackupImportError(f"Plik {filename} zawiera pusty lub zduplikowany identyfikator.")
                result[filename] = rows
            _validate_duplicates(result)
            _validate_semantics(result)
            return result
    except (BadZipFile, OSError) as error:
        raise BackupImportError("Plik nie jest prawidłowym archiwum ZIP z CSV.") from error


def _bool(value):
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "tak", "yes"}:
        return True
    if normalized in {"0", "false", "nie", "no", ""}:
        return False
    raise BackupImportError(f"Nieprawidłowa wartość logiczna: {value}.")


def _decimal(value, *, nullable=False):
    if value in (None, "") and nullable:
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation as error:
        raise BackupImportError(f"Nieprawidłowa liczba: {value}.") from error


def _int(value, *, nullable=False):
    if value in (None, "") and nullable:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise BackupImportError(f"Nieprawidłowa liczba całkowita: {value}.") from error


def _date(value, *, nullable=False):
    if not value and nullable:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise BackupImportError(f"Nieprawidłowa data: {value}.") from error


def _time(value):
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise BackupImportError(f"Nieprawidłowa godzina: {value}.") from error


def _datetime(value):
    if not value:
        return None
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(value)
    if parsed is None:
        raise BackupImportError(f"Nieprawidłowa data i godzina: {value}.")
    return parsed


def _related(mapping, old_id, label):
    try:
        return mapping[str(old_id)]
    except KeyError as error:
        raise BackupImportError(f"Brak relacji {label} dla ID {old_id}.") from error


def _validate_duplicates(rows):
    unique_fields = {
        "vaccination_plans.csv": ("name",),
        "ingredients.csv": ("name",),
        "recipes.csv": ("name",),
        "recipe_items.csv": ("recipe_id", "ingredient_id"),
        "sale_rows.csv": ("sale_id", "line_no"),
        "cost_categories.csv": ("name",),
    }
    for filename, fields in unique_fields.items():
        seen = set()
        for row in rows[filename]:
            key = tuple((row[field] or "").strip().casefold() for field in fields)
            if key in seen:
                raise BackupImportError(f"Plik {filename} zawiera zduplikowany rekord ({', '.join(key)}).")
            seen.add(key)

    active_sow_tags = set()
    for row in rows["sows.csv"]:
        if _bool(row["is_archived"]):
            continue
        ear_tag = row["ear_tag"].strip().casefold()
        if ear_tag in active_sow_tags:
            raise BackupImportError(
                f"Plik sows.csv zawiera zduplikowany numer aktywnej maciory ({ear_tag})."
            )
        active_sow_tags.add(ear_tag)

    sale_documents = set()
    for row in rows["sales.csv"]:
        document_number = row["document_number"].strip().casefold()
        sale_date = row["sale_date"].strip()
        if not document_number:
            continue
        if not sale_date:
            raise BackupImportError(
                "Sprzedaż z numerem dokumentu musi zawierać datę sprzedaży."
            )
        key = (sale_date[:4], document_number)
        if key in sale_documents:
            raise BackupImportError(
                f"Plik sales.csv zawiera zduplikowany numer dokumentu w roku {key[0]} ({document_number})."
            )
        sale_documents.add(key)


def _validate_semantics(rows):
    required_text = {
        "sows.csv": "ear_tag",
        "vaccination_plans.csv": "name",
        "ingredients.csv": "name",
        "recipes.csv": "name",
        "cost_categories.csv": "name",
    }
    for filename, field in required_text.items():
        if any(not row[field].strip() for row in rows[filename]):
            raise BackupImportError(f"Plik {filename} zawiera pustą wartość w kolumnie {field}.")
    event_types = {"INSEMINATION", "PREGNANCY_CHECK", "FARROWING", "WEANING", "VACCINATION"}
    if any(row["event_type"] not in event_types for row in rows["sow_events.csv"]):
        raise BackupImportError("sow_events.csv zawiera nieobsługiwany typ zdarzenia.")
    cycle_statuses = {"COMPLETED", "SKIPPED"}
    if any(row["status"] not in cycle_statuses for row in rows["vaccination_cycles.csv"]):
        raise BackupImportError("vaccination_cycles.csv zawiera nieobsługiwany status.")
    statuses = {choice for choice, _ in ProductionModel.Statuses.choices}
    if any(row["status"] not in statuses for row in rows["productions.csv"]):
        raise BackupImportError("productions.csv zawiera nieobsługiwany status.")
    recipe_totals = {}
    for row in rows["recipe_items.csv"]:
        recipe_totals[row["recipe_id"]] = recipe_totals.get(row["recipe_id"], Decimal("0")) + _decimal(row["percentage"])
    recipe_ids = {row["id"] for row in rows["recipes.csv"]}
    if set(recipe_totals) != recipe_ids or any(total != Decimal("100") for total in recipe_totals.values()):
        raise BackupImportError("Pozycje każdej receptury muszą sumować się do 100%.")


@transaction.atomic
def import_csv_archive(uploaded_file, farm) -> dict[str, int]:
    existing = user_business_data_counts(farm)
    if existing:
        raise BackupImportError("Import CSV jest dozwolony tylko do pustego gospodarstwa.")
    rows = _read_archive(uploaded_file)
    counts = {}
    sow_map = {}
    for row in rows["sows.csv"]:
        sow_map[row["id"]] = SowModel.objects.create(
            farm=farm,
            ear_tag=row["ear_tag"].strip(),
            entry_date=_date(row["entry_date"]),
            is_archived=_bool(row["is_archived"]),
            archived_at=_datetime(row["archived_at"]),
        )
    counts["maciory"] = len(sow_map)
    plan_map = {}
    plan_relation_rows = []
    for row in rows["vaccination_plans.csv"]:
        legacy_interval = _int(row.get("interval_months"), nullable=True)
        interval_value = _int(row.get("interval_value"), nullable=True) or legacy_interval
        first_due_date = _date(row.get("first_due_date"), nullable=True)
        plan = VaccinationPlanModel.objects.create(
            farm=farm,
            name=row["name"].strip(),
            days_before_farrowing=_int(row["days_before_farrowing"], nullable=True),
            days_after_event=_int(row["days_after_event"], nullable=True),
            event_source=row["event_source"] or None,
            interval_months=legacy_interval,
            interval_value=interval_value,
            interval_unit=row.get("interval_unit") or ("MONTHS" if interval_value else None),
            schedule_mode=row.get("schedule_mode") or ("FROM_LAST_COMPLETED" if interval_value else None),
            first_due_date=first_due_date,
            scope=row.get("scope") or "ALL",
            is_active=_bool(row["is_active"]) if row.get("is_active") not in (None, "") else not (interval_value and not first_due_date),
            requires_configuration=_bool(row["requires_configuration"]) if row.get("requires_configuration") not in (None, "") else bool(interval_value and not first_due_date),
            reminder_days_ahead=_int(row["reminder_days_ahead"] or 7),
        )
        plan_map[row["id"]] = plan
        plan_relation_rows.append((plan, row))
    counts["plany szczepień"] = len(rows["vaccination_plans.csv"])
    for plan, row in plan_relation_rows:
        for field_name, column in (
            ("selected_sows", "selected_sow_ids"),
            ("excluded_sows", "excluded_sow_ids"),
        ):
            try:
                sow_ids = json.loads(row.get(column) or "[]")
            except json.JSONDecodeError as error:
                raise BackupImportError(f"Nieprawidłowy JSON w kolumnie {column}.") from error
            getattr(plan, field_name).add(*[
                _related(sow_map, str(sow_id), "maciory")
                for sow_id in sow_ids
            ])

    matched_legacy_plan_ids = set()
    plans_by_name = {}
    for plan in plan_map.values():
        plans_by_name.setdefault(plan.name.casefold(), []).append(plan)
    event_map = {}
    for row in rows["sow_events.csv"]:
        try:
            details = json.loads(row["details"] or "{}")
        except json.JSONDecodeError as error:
            raise BackupImportError("Nieprawidłowy JSON w sow_events.csv.") from error
        plan_id = row.get("vaccination_plan_id")
        plan = _related(plan_map, plan_id, "plany szczepień") if plan_id else None
        vaccine_name = row.get("vaccine_name") or details.get("vaccine_name", "")
        if plan is None and vaccine_name:
            candidates = plans_by_name.get(str(vaccine_name).casefold(), [])
            plan = candidates[0] if len(candidates) == 1 else None
        if plan:
            matched_legacy_plan_ids.add(plan.id)
        event = SowEventModel.objects.create(
            sow=_related(sow_map, row["sow_id"], "maciory"),
            event_type=row["event_type"],
            event_date=_date(row["event_date"]),
            details=details,
            vaccination_plan=plan,
            vaccine_name=vaccine_name,
            cycle_id=row.get("cycle_id") or details.get("cycle_id", ""),
            scheduled_date=_date(row.get("scheduled_date"), nullable=True),
        )
        event_map[row["id"]] = event
    counts["zdarzenia macior"] = len(rows["sow_events.csv"])
    for row in rows["piglet_transfers.csv"]:
        PigletTransferModel.objects.create(
            farm=farm,
            source_farrowing=_related(event_map, row["source_farrowing_id"], "oproszenia źródłowe"),
            target_farrowing=_related(event_map, row["target_farrowing_id"], "oproszenia docelowe"),
            quantity=_int(row["quantity"]),
            transfer_date=_date(row["transfer_date"]),
            note=row.get("note") or "",
            canceled_at=_datetime(row.get("canceled_at")),
            cancellation_note=row.get("cancellation_note") or "",
        )
    counts["przeniesienia prosiąt"] = len(rows["piglet_transfers.csv"])
    for plan in plan_map.values():
        if plan.interval_value and plan.first_due_date is None and plan.id in matched_legacy_plan_ids:
            plan.is_active = True
            plan.requires_configuration = False
            plan.save(update_fields=("is_active", "requires_configuration"))
    for row in rows["vaccination_cycles.csv"]:
        VaccinationCycleModel.objects.create(
            plan=_related(plan_map, row["plan_id"], "plany szczepień"),
            sow=_related(sow_map, row["sow_id"], "maciory"),
            cycle_id=row["cycle_id"],
            scheduled_date=_date(row["scheduled_date"]),
            status=row["status"],
            completed_at=_date(row["completed_at"], nullable=True),
            skipped_at=_date(row["skipped_at"], nullable=True),
            note=row["note"],
        )
    counts["cykle szczepień"] = len(rows["vaccination_cycles.csv"])
    mortality_types = {value for value, _label in MortalityReportModel.TYPE_CHOICES}
    for row in rows["mortality.csv"]:
        if row.get("source") == "automatic":
            continue
        mortality_type = {
            "sow": MortalityReportModel.TYPE_SOW,
            "post_weaning": MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
            "": MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
        }.get(row.get("mortality_type"), row.get("mortality_type"))
        if mortality_type not in mortality_types:
            raise BackupImportError("mortality.csv zawiera nieobsługiwany typ upadku.")
        sow = _related(sow_map, row["sow_id"], "maciory") if row.get("sow_id") else None
        farrowing = _related(event_map, row["farrowing_id"], "cykle odchowu") if row.get("farrowing_id") else None
        MortalityReportModel.objects.create(
            farm=farm,
            mortality_type=mortality_type,
            sow=sow,
            farrowing=farrowing,
            mortality_date=_date(row["mortality_date"]),
            quantity=_int(row["quantity"]),
            reason=row.get("reason") or "",
            note=row.get("note") or "",
        )
    counts["upadki"] = sum(row.get("source") != "automatic" for row in rows["mortality.csv"])
    ingredient_map = {}
    for row in rows["ingredients.csv"]:
        ingredient_map[row["id"]] = IngredientModel.objects.create(farm=farm, name=row["name"].strip(), description=row["description"] or None, low_stock_threshold_kg=_decimal(row["low_stock_threshold_kg"]), is_in_bin=_bool(row["is_in_bin"]))
    recipe_map = {row["id"]: RecipeModel.objects.create(farm=farm, name=row["name"].strip()) for row in rows["recipes.csv"]}
    for row in rows["recipe_items.csv"]:
        RecipeItemModel.objects.create(recipe=_related(recipe_map, row["recipe_id"], "receptury"), ingredient=_related(ingredient_map, row["ingredient_id"], "składniki"), percentage=_decimal(row["percentage"]))
    for row in rows["deliveries.csv"]:
        DeliveryModel.objects.create(ingredient=_related(ingredient_map, row["ingredient_id"], "składniki"), date=_date(row["date"]), quantity_kg=_decimal(row["quantity_kg"]), price_per_kg=_decimal(row["price_per_kg"], nullable=True))
    production_map = {}
    for row in rows["productions.csv"]:
        try:
            custom = json.loads(row["custom_recipe_data"] or "null")
        except json.JSONDecodeError as error:
            raise BackupImportError("Nieprawidłowy JSON w productions.csv.") from error
        if isinstance(custom, dict):
            custom = {str(_related(ingredient_map, key, "składniki").pk): value for key, value in custom.items()}
        production = ProductionModel(
            recipe=_related(recipe_map, row["recipe_id"], "receptury"),
            date=_date(row["date"]),
            time=_time(row["time"]),
            quantity_kg=_decimal(row["quantity_kg"]),
            custom_recipe_data=custom,
            status=ProductionModel.Statuses.QUEUED,
            completed_at=_datetime(row["completed_at"]),
        )
        production._skip_inventory_sync = True
        production.save()
        ProductionModel.objects.filter(pk=production.pk).update(
            status=row["status"],
            completed_at=_datetime(row["completed_at"]),
        )
        production.status = row["status"]
        production_map[row["id"]] = production
    sale_map = {}
    decimal_fields = ("total_weight", "price_per_kg", "avg_meatiness_seurop", "live_weight", "dressing_percentage", "net_value", "vat_value", "gross_value")
    for row in rows["sales.csv"]:
        values = {name: _decimal(row[name], nullable=name in {"avg_meatiness_seurop", "live_weight", "dressing_percentage"}) for name in decimal_fields}
        sale_map[row["id"]] = PigSaleModel.objects.create(farm=farm, sale_date=_date(row["sale_date"], nullable=True), document_number=row["document_number"].strip(), tattoo=row["tattoo"], no_settlement=_bool(row["no_settlement"]), quantity=_int(row["quantity"] or 0), meat_class=row["meat_class"], **values)
    for row in rows["sale_rows.csv"]:
        SaleClassRowModel.objects.create(sale=_related(sale_map, row["sale_id"], "sprzedaże"), line_no=_int(row["line_no"]), meat_class=row["meat_class"], quantity=_int(row["quantity"], nullable=True), **{name: _decimal(row[name], nullable=True) for name in ("weight", "avg_weight", "avg_meatiness", "price_per_kg", "net_value", "vat_value", "gross_value")})
    category_map = {}
    for row in rows["cost_categories.csv"]:
        category_map[row["id"]] = CostCategoryModel.objects.create(
            farm=farm,
            name=row["name"].strip(),
            description=row["description"],
            is_active=_bool(row["is_active"]),
        )
    for row in rows["costs.csv"]:
        category = None
        if row["category_id"]:
            category = _related(category_map, row["category_id"], "kategorii kosztu")
        production_id = row.get("production_id") or ""
        defaults = {
            "farm": farm,
            "category": category,
            "date": _date(row["date"]),
            "amount": _decimal(row["amount"]),
            "description": row["description"],
            "document_number": row["document_number"],
            "supplier": row["supplier"],
            "is_paid": _bool(row["is_paid"]),
        }
        if production_id:
            CostModel.objects.update_or_create(
                production=_related(production_map, production_id, "produkcji"),
                defaults=defaults,
            )
        else:
            CostModel.objects.create(**defaults)
    InventoryActions(farm).rebuild()
    counts.update({"składniki": len(ingredient_map), "receptury": len(recipe_map), "dostawy": len(rows["deliveries.csv"]), "produkcje": len(rows["productions.csv"]), "sprzedaże": len(sale_map), "wiersze sprzedaży": len(rows["sale_rows.csv"]), "kategorie kosztów": len(category_map), "koszty": len(rows["costs.csv"])})
    return counts
