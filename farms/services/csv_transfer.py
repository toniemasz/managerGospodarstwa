from __future__ import annotations

import csv
import json
from datetime import date, time
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from django.db import transaction

from farms.services.data_backup import BackupImportError, user_business_data_counts
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.services.inventory_service import InventoryMovementService
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


MAX_CSV_ARCHIVE_SIZE = 25 * 1024 * 1024

SCHEMAS = {
    "sows.csv": ("id", "ear_tag", "entry_date", "is_archived", "archived_at"),
    "sow_events.csv": ("id", "sow_id", "event_type", "event_date", "details"),
    "vaccination_plans.csv": ("id", "name", "days_before_farrowing", "days_after_event", "event_source", "interval_months", "reminder_days_ahead"),
    "ingredients.csv": ("id", "name", "description", "low_stock_threshold_kg", "is_in_bin"),
    "deliveries.csv": ("id", "ingredient_id", "date", "quantity_kg", "price_per_kg"),
    "recipes.csv": ("id", "name"),
    "recipe_items.csv": ("id", "recipe_id", "ingredient_id", "percentage"),
    "productions.csv": ("id", "recipe_id", "date", "time", "quantity_kg", "custom_recipe_data", "status", "completed_at"),
    "sales.csv": ("id", "sale_date", "document_number", "tattoo", "no_settlement", "quantity", "total_weight", "meat_class", "price_per_kg", "avg_meatiness_seurop", "live_weight", "dressing_percentage", "net_value", "vat_value", "gross_value"),
    "sale_rows.csv": ("id", "sale_id", "line_no", "meat_class", "quantity", "weight", "avg_weight", "avg_meatiness", "price_per_kg", "net_value", "vat_value", "gross_value"),
}


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


def build_csv_export(farm) -> tuple[bytes, str]:
    datasets = {
        "sows.csv": [
            {"id": obj.pk, "ear_tag": obj.ear_tag, "entry_date": obj.entry_date, "is_archived": obj.is_archived, "archived_at": obj.archived_at}
            for obj in SowModel.objects.filter(farm=farm).order_by("id")
        ],
        "sow_events.csv": [
            {"id": obj.pk, "sow_id": obj.sow_id, "event_type": obj.event_type, "event_date": obj.event_date, "details": obj.details}
            for obj in SowEventModel.objects.filter(sow__farm=farm).order_by("id")
        ],
        "vaccination_plans.csv": [
            {column: getattr(obj, column) for column in SCHEMAS["vaccination_plans.csv"]}
            for obj in VaccinationPlanModel.objects.filter(farm=farm).order_by("id")
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
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for filename, columns in SCHEMAS.items():
            archive.writestr(filename, _write_csv(columns, datasets[filename]))
    from django.utils import timezone
    return buffer.getvalue(), f"eksport_csv_{timezone.now():%Y-%m-%d_%H-%M-%S}.zip"


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
            missing = set(SCHEMAS) - names
            if missing:
                raise BackupImportError(f"Brak wymaganych plików: {', '.join(sorted(missing))}.")
            result = {}
            for filename, required in SCHEMAS.items():
                try:
                    text = archive.read(filename).decode("utf-8-sig")
                except UnicodeDecodeError as error:
                    raise BackupImportError(f"Plik {filename} nie jest zapisany w UTF-8.") from error
                reader = csv.DictReader(StringIO(text))
                columns = tuple(reader.fieldnames or ())
                missing_columns = set(required) - set(columns)
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
        "sows.csv": ("ear_tag",),
        "vaccination_plans.csv": ("name",),
        "ingredients.csv": ("name",),
        "recipes.csv": ("name",),
        "recipe_items.csv": ("recipe_id", "ingredient_id"),
        "sale_rows.csv": ("sale_id", "line_no"),
    }
    for filename, fields in unique_fields.items():
        seen = set()
        for row in rows[filename]:
            key = tuple((row[field] or "").strip().casefold() for field in fields)
            if key in seen:
                raise BackupImportError(f"Plik {filename} zawiera zduplikowany rekord ({', '.join(key)}).")
            seen.add(key)


def _validate_semantics(rows):
    required_text = {
        "sows.csv": "ear_tag",
        "vaccination_plans.csv": "name",
        "ingredients.csv": "name",
        "recipes.csv": "name",
    }
    for filename, field in required_text.items():
        if any(not row[field].strip() for row in rows[filename]):
            raise BackupImportError(f"Plik {filename} zawiera pustą wartość w kolumnie {field}.")
    event_types = {"INSEMINATION", "PREGNANCY_CHECK", "FARROWING", "WEANING", "VACCINATION"}
    if any(row["event_type"] not in event_types for row in rows["sow_events.csv"]):
        raise BackupImportError("sow_events.csv zawiera nieobsługiwany typ zdarzenia.")
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
            ear_tag=row["ear_tag"],
            entry_date=_date(row["entry_date"]),
            is_archived=_bool(row["is_archived"]),
            archived_at=_datetime(row["archived_at"]),
        )
    counts["maciory"] = len(sow_map)
    for row in rows["sow_events.csv"]:
        try:
            details = json.loads(row["details"] or "{}")
        except json.JSONDecodeError as error:
            raise BackupImportError("Nieprawidłowy JSON w sow_events.csv.") from error
        SowEventModel.objects.create(sow=_related(sow_map, row["sow_id"], "maciory"), event_type=row["event_type"], event_date=_date(row["event_date"]), details=details)
    counts["zdarzenia macior"] = len(rows["sow_events.csv"])
    for row in rows["vaccination_plans.csv"]:
        VaccinationPlanModel.objects.create(
            farm=farm,
            name=row["name"],
            days_before_farrowing=_int(row["days_before_farrowing"], nullable=True),
            days_after_event=_int(row["days_after_event"], nullable=True),
            event_source=row["event_source"] or None,
            interval_months=_int(row["interval_months"], nullable=True),
            reminder_days_ahead=_int(row["reminder_days_ahead"] or 7),
        )
    counts["plany szczepień"] = len(rows["vaccination_plans.csv"])
    ingredient_map = {}
    for row in rows["ingredients.csv"]:
        ingredient_map[row["id"]] = IngredientModel.objects.create(farm=farm, name=row["name"], description=row["description"] or None, low_stock_threshold_kg=_decimal(row["low_stock_threshold_kg"]), is_in_bin=_bool(row["is_in_bin"]))
    recipe_map = {row["id"]: RecipeModel.objects.create(farm=farm, name=row["name"]) for row in rows["recipes.csv"]}
    for row in rows["recipe_items.csv"]:
        RecipeItemModel.objects.create(recipe=_related(recipe_map, row["recipe_id"], "receptury"), ingredient=_related(ingredient_map, row["ingredient_id"], "składniki"), percentage=_decimal(row["percentage"]))
    for row in rows["deliveries.csv"]:
        DeliveryModel.objects.create(ingredient=_related(ingredient_map, row["ingredient_id"], "składniki"), date=_date(row["date"]), quantity_kg=_decimal(row["quantity_kg"]), price_per_kg=_decimal(row["price_per_kg"], nullable=True))
    for row in rows["productions.csv"]:
        try:
            custom = json.loads(row["custom_recipe_data"] or "null")
        except json.JSONDecodeError as error:
            raise BackupImportError("Nieprawidłowy JSON w productions.csv.") from error
        if isinstance(custom, dict):
            custom = {str(_related(ingredient_map, key, "składniki").pk): value for key, value in custom.items()}
        ProductionModel.objects.create(
            recipe=_related(recipe_map, row["recipe_id"], "receptury"),
            date=_date(row["date"]),
            time=_time(row["time"]),
            quantity_kg=_decimal(row["quantity_kg"]),
            custom_recipe_data=custom,
            status=row["status"],
            completed_at=_datetime(row["completed_at"]),
        )
    sale_map = {}
    decimal_fields = ("total_weight", "price_per_kg", "avg_meatiness_seurop", "live_weight", "dressing_percentage", "net_value", "vat_value", "gross_value")
    for row in rows["sales.csv"]:
        values = {name: _decimal(row[name], nullable=name in {"avg_meatiness_seurop", "live_weight", "dressing_percentage"}) for name in decimal_fields}
        sale_map[row["id"]] = PigSaleModel.objects.create(farm=farm, sale_date=_date(row["sale_date"], nullable=True), document_number=row["document_number"], tattoo=row["tattoo"], no_settlement=_bool(row["no_settlement"]), quantity=_int(row["quantity"] or 0), meat_class=row["meat_class"], **values)
    for row in rows["sale_rows.csv"]:
        SaleClassRowModel.objects.create(sale=_related(sale_map, row["sale_id"], "sprzedaże"), line_no=_int(row["line_no"]), meat_class=row["meat_class"], quantity=_int(row["quantity"], nullable=True), **{name: _decimal(row[name], nullable=True) for name in ("weight", "avg_weight", "avg_meatiness", "price_per_kg", "net_value", "vat_value", "gross_value")})
    InventoryMovementService(farm).rebuild()
    counts.update({"składniki": len(ingredient_map), "receptury": len(recipe_map), "dostawy": len(rows["deliveries.csv"]), "produkcje": len(rows["productions.csv"]), "sprzedaże": len(sale_map), "wiersze sprzedaży": len(rows["sale_rows.csv"])})
    return counts
