from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from farms.services.cache import invalidate_farm_cache_on_commit
from sows.models import MortalityReportModel, SowModel


@dataclass(frozen=True)
class MortalityReportResult:
    report: MortalityReportModel
    archived_sow: bool = False


@transaction.atomic
def create_mortality_report(*, farm, user=None, data: dict) -> MortalityReportResult:
    mortality_type = data["mortality_type"]
    sow = data.get("sow")
    quantity = data.get("quantity")

    if mortality_type == MortalityReportModel.TYPE_SOW:
        sow = _get_active_sow_for_mortality(farm=farm, sow=sow)
        quantity = 1
    elif mortality_type == MortalityReportModel.TYPE_POST_WEANING:
        sow = None
        if quantity is None or quantity <= 0:
            raise ValidationError("Podaj liczbę sztuk większą od zera.")

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

    archived_sow = False
    if mortality_type == MortalityReportModel.TYPE_SOW:
        _archive_sow_because_of_death(sow=sow, report=report)
        archived_sow = True

    invalidate_farm_cache_on_commit(farm, groups=("sows",))
    return MortalityReportResult(report=report, archived_sow=archived_sow)


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
