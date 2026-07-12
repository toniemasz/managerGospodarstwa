from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from common.cache import invalidate_farm_cache_on_commit
from sows.models import MortalityReportModel, SowModel


@dataclass(frozen=True)
class MortalityReportResult:
    report: MortalityReportModel
    archived_sow: bool = False


@transaction.atomic
def update_mortality_report(*, farm, report_id: int, data: dict) -> MortalityReportModel:
    report = MortalityReportModel.objects.select_for_update().filter(pk=report_id, farm=farm).first()
    if report is None:
        raise ValidationError("Nie znaleziono zgłoszenia upadku w bieżącym gospodarstwie.")
    if report.mortality_type == MortalityReportModel.TYPE_SOW:
        raise ValidationError("Upadku maciory nie można zmieniać po zarchiwizowaniu maciory.")
    mortality_type = data["mortality_type"]
    if mortality_type not in MortalityReportModel.POST_WEANING_TYPES[:3]:
        raise ValidationError("Rekord można przeklasyfikować na prosiaka, warchlaka albo tucznika.")
    quantity = data.get("quantity")
    if quantity is None or quantity <= 0:
        raise ValidationError("Podaj liczbę sztuk większą od zera.")
    report.mortality_type = mortality_type
    report.sow = None
    report.quantity = quantity
    report.mortality_date = data["mortality_date"]
    report.reason = data.get("reason") or ""
    report.note = data.get("note") or ""
    report.save(update_fields=("mortality_type", "sow", "quantity", "mortality_date", "reason", "note"))
    invalidate_farm_cache_on_commit(farm, groups=("sows",))
    return report


@transaction.atomic
def delete_mortality_report(*, farm, report_id: int) -> MortalityReportModel:
    report = MortalityReportModel.objects.select_for_update().filter(pk=report_id, farm=farm).first()
    if report is None:
        raise ValidationError("Nie znaleziono zgłoszenia upadku w bieżącym gospodarstwie.")
    if report.mortality_type == MortalityReportModel.TYPE_SOW:
        raise ValidationError("Upadku maciory nie można usunąć bez kontrolowanego przywrócenia maciory.")
    report.delete()
    invalidate_farm_cache_on_commit(farm, groups=("sows",))
    return report


@transaction.atomic
def create_mortality_report(*, farm, user=None, data: dict) -> MortalityReportResult:
    mortality_type = _normalize_mortality_type(data["mortality_type"])
    sow = data.get("sow")
    quantity = data.get("quantity")

    if mortality_type == MortalityReportModel.TYPE_SOW:
        sow = _get_active_sow_for_mortality(farm=farm, sow=sow)
        quantity = 1
    elif mortality_type in MortalityReportModel.POST_WEANING_TYPES[:3]:
        sow = None
        if quantity is None or quantity <= 0:
            raise ValidationError("Podaj liczbę sztuk większą od zera.")

    elif mortality_type not in {value for value, _label in MortalityReportModel.MANUAL_TYPE_CHOICES}:
        raise ValidationError("Nieobsługiwany typ upadku.")

    try:
        report = MortalityReportModel.objects.create(
            farm=farm,
            mortality_type=mortality_type,
            sow=sow,
            mortality_date=data["mortality_date"],
            quantity=quantity,
            reason=data.get("reason") or "",
            note=data.get("note") or "",
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
    except IntegrityError as error:
        raise ValidationError("Nie można zapisać upadku z podanym typem i maciorą.") from error

    archived_sow = False
    if mortality_type == MortalityReportModel.TYPE_SOW:
        _archive_sow_because_of_death(sow=sow, report=report)
        archived_sow = True

    invalidate_farm_cache_on_commit(farm, groups=("sows",))
    return MortalityReportResult(report=report, archived_sow=archived_sow)


def _normalize_mortality_type(value: str) -> str:
    if value == "sow":
        return MortalityReportModel.TYPE_SOW
    if value == "post_weaning":
        raise ValidationError(
            "Wybierz dokładny typ upadku: Prosiak, Warchlak albo Tucznik."
        )
    return value


def _get_active_sow_for_mortality(*, farm, sow) -> SowModel:
    if sow is None:
        raise ValidationError("Wybierz aktywną maciorę.")
    locked_sow = (
        SowModel.objects
        .select_for_update()
        .filter(pk=sow.pk, farm=farm, is_archived=False)
        .first()
    )
    if locked_sow is None:
        raise ValidationError("Nie można zgłosić upadku tej maciory.")
    return locked_sow


def _archive_sow_because_of_death(*, sow: SowModel, report: MortalityReportModel) -> None:
    sow.is_archived = True
    sow.archived_at = timezone.now()
    sow.archive_reason = SowModel.ARCHIVE_REASON_DEATH
    sow.death_date = report.mortality_date
    sow.death_note = report.note
    sow.save(update_fields=[
        "is_archived",
        "archived_at",
        "archive_reason",
        "death_date",
        "death_note",
    ])
