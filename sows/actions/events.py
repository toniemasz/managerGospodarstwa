from __future__ import annotations

from datetime import date

from django.db import transaction
from django.shortcuts import get_object_or_404

from sows.models import SowEventModel, SowModel


PREGNANCY_CHECK_RESULTS = {"TAK", "NIE", "?"}


@transaction.atomic
def record_bulk_pregnancy_checks(
    *,
    farm,
    sows,
    results_by_sow_id: dict,
    event_date=None,
) -> list[SowEventModel]:
    event_date = event_date or date.today()
    events = []

    for sow in sows:
        result = results_by_sow_id.get(sow.id)
        if result is None:
            result = results_by_sow_id.get(str(sow.id))
        if result not in PREGNANCY_CHECK_RESULTS:
            continue

        db_sow = get_object_or_404(SowModel, id=sow.id, farm=farm)
        events.append(SowEventModel.objects.create(
            sow=db_sow,
            event_type="PREGNANCY_CHECK",
            event_date=event_date,
            details={"result": result},
        ))

    return events


@transaction.atomic
def record_bulk_vaccinations(
    *,
    farm,
    sow_ids: list,
    vaccine_name: str,
    cycle_id: str,
    event_date=None,
) -> list[SowEventModel]:
    event_date = event_date or date.today()
    events = []

    for sow_id in sow_ids:
        sow = get_object_or_404(SowModel, id=sow_id, farm=farm)
        events.append(SowEventModel.objects.create(
            sow=sow,
            event_type="VACCINATION",
            event_date=event_date,
            details={
                "vaccine_name": vaccine_name,
                "cycle_id": cycle_id,
            },
        ))

    return events
