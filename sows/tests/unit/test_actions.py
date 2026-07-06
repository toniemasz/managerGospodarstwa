from types import SimpleNamespace
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.http import Http404

from farms.services.farm_service import get_or_create_user_farm
from sows.actions.events import record_bulk_pregnancy_checks, record_bulk_vaccinations
from sows.models import SowEventModel, SowModel


@pytest.fixture
def farm():
    user = User.objects.create_user(username="sow-action-user")
    return get_or_create_user_farm(user)


@pytest.mark.django_db
def test_record_bulk_pregnancy_checks_creates_only_submitted_results(farm):
    sow_with_result = SowModel.objects.create(ear_tag="USG-ACTION-1", farm=farm)
    sow_without_result = SowModel.objects.create(ear_tag="USG-ACTION-2", farm=farm)

    events = record_bulk_pregnancy_checks(
        farm=farm,
        sows=[
            SimpleNamespace(id=sow_with_result.id),
            SimpleNamespace(id=sow_without_result.id),
        ],
        results_by_sow_id={
            str(sow_with_result.id): "TAK",
            str(sow_without_result.id): "IGNORED",
        },
        event_date=date(2026, 7, 1),
    )

    assert len(events) == 1
    event = SowEventModel.objects.get()
    assert event.sow == sow_with_result
    assert event.event_type == "PREGNANCY_CHECK"
    assert event.event_date == date(2026, 7, 1)
    assert event.details == {"result": "TAK"}


@pytest.mark.django_db
def test_record_bulk_vaccinations_creates_events_for_farm_sows(farm):
    sow = SowModel.objects.create(ear_tag="VAC-ACTION-1", farm=farm)

    events = record_bulk_vaccinations(
        farm=farm,
        sow_ids=[str(sow.id)],
        vaccine_name="Parwo",
        cycle_id="cyclic_2026-07-01",
        event_date=date(2026, 7, 1),
    )

    assert len(events) == 1
    event = SowEventModel.objects.get()
    assert event.sow == sow
    assert event.event_type == "VACCINATION"
    assert event.event_date == date(2026, 7, 1)
    assert event.details == {
        "vaccine_name": "Parwo",
        "cycle_id": "cyclic_2026-07-01",
    }


@pytest.mark.django_db
def test_record_bulk_vaccinations_rolls_back_when_sow_is_outside_farm(farm):
    own_sow = SowModel.objects.create(ear_tag="VAC-ACTION-OWN", farm=farm)
    other_user = User.objects.create_user(username="sow-action-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_sow = SowModel.objects.create(ear_tag="VAC-ACTION-FOREIGN", farm=other_farm)

    with pytest.raises(Http404):
        record_bulk_vaccinations(
            farm=farm,
            sow_ids=[str(own_sow.id), str(foreign_sow.id)],
            vaccine_name="Parwo",
            cycle_id="cyclic_2026-07-01",
            event_date=date(2026, 7, 1),
        )

    assert not SowEventModel.objects.filter(sow=own_sow).exists()
    assert not SowEventModel.objects.filter(sow=foreign_sow).exists()
