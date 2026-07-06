from types import SimpleNamespace
from datetime import date

import pytest
from django.contrib.auth.models import User
from django.http import Http404

from farms.services.farm_service import get_or_create_user_farm
from sows.actions.events import SowEventActions
from sows.models import SowEventModel, SowModel


@pytest.fixture
def farm():
    user = User.objects.create_user(username="sow-action-user")
    return get_or_create_user_farm(user)


@pytest.mark.django_db
def test_bulk_create_pregnancy_checks_creates_only_submitted_results(farm):
    sow_with_result = SowModel.objects.create(ear_tag="USG-ACTION-1", farm=farm)
    sow_without_result = SowModel.objects.create(ear_tag="USG-ACTION-2", farm=farm)

    events = SowEventActions(farm=farm).bulk_create_pregnancy_checks(
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
def test_bulk_create_vaccinations_creates_events_for_farm_sows(farm):
    sow = SowModel.objects.create(ear_tag="VAC-ACTION-1", farm=farm)

    events = SowEventActions(farm=farm).bulk_create_vaccinations(
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
def test_bulk_create_vaccinations_rolls_back_when_sow_is_outside_farm(farm):
    own_sow = SowModel.objects.create(ear_tag="VAC-ACTION-OWN", farm=farm)
    other_user = User.objects.create_user(username="sow-action-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_sow = SowModel.objects.create(ear_tag="VAC-ACTION-FOREIGN", farm=other_farm)

    with pytest.raises(Http404):
        SowEventActions(farm=farm).bulk_create_vaccinations(
            sow_ids=[str(own_sow.id), str(foreign_sow.id)],
            vaccine_name="Parwo",
            cycle_id="cyclic_2026-07-01",
            event_date=date(2026, 7, 1),
        )

    assert not SowEventModel.objects.filter(sow=own_sow).exists()
    assert not SowEventModel.objects.filter(sow=foreign_sow).exists()


@pytest.mark.django_db
def test_create_event_uses_single_event_service_flow(farm):
    sow = SowModel.objects.create(ear_tag="CREATE-ACTION-1", farm=farm)

    result = SowEventActions(farm=farm).create_event(
        sow=sow,
        sow_status="IDLE",
        data={
            "event_type": "INSEMINATION",
            "event_date": date(2026, 7, 2),
            "technician": "Jan",
        },
    )

    assert result.created_event == SowEventModel.objects.get(sow=sow)
    assert result.created_event.details == {"technician": "Jan"}


@pytest.mark.django_db
def test_update_event_is_farm_scoped_and_rebuilds_details(farm):
    sow = SowModel.objects.create(ear_tag="UPDATE-ACTION-1", farm=farm)
    event = SowEventModel.objects.create(
        sow=sow,
        event_type="INSEMINATION",
        event_date=date(2026, 7, 1),
        details={"technician": "Jan"},
    )

    updated_event = SowEventActions(farm=farm).update_event(
        event_id=event.id,
        data={
            "event_type": "PREGNANCY_CHECK",
            "event_date": date(2026, 7, 30),
            "pregnancy_result": "TAK",
        },
    )

    event.refresh_from_db()
    assert updated_event.id == event.id
    assert event.event_type == "PREGNANCY_CHECK"
    assert event.event_date == date(2026, 7, 30)
    assert event.details == {"result": "TAK"}


@pytest.mark.django_db
def test_update_event_rejects_event_from_other_farm(farm):
    other_user = User.objects.create_user(username="sow-action-update-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_sow = SowModel.objects.create(ear_tag="UPDATE-ACTION-FOREIGN", farm=other_farm)
    foreign_event = SowEventModel.objects.create(
        sow=foreign_sow,
        event_type="INSEMINATION",
        event_date=date(2026, 7, 1),
        details={"technician": "Jan"},
    )

    with pytest.raises(Http404):
        SowEventActions(farm=farm).update_event(
            event_id=foreign_event.id,
            data={
                "event_type": "PREGNANCY_CHECK",
                "event_date": date(2026, 7, 30),
                "pregnancy_result": "TAK",
            },
        )

    foreign_event.refresh_from_db()
    assert foreign_event.event_type == "INSEMINATION"
    assert foreign_event.details == {"technician": "Jan"}


@pytest.mark.django_db
def test_delete_event_returns_audit_data_and_removes_event(farm):
    sow = SowModel.objects.create(ear_tag="DELETE-ACTION-1", farm=farm)
    event = SowEventModel.objects.create(
        sow=sow,
        event_type="INSEMINATION",
        event_date=date(2026, 7, 1),
        details={"technician": "Jan"},
    )

    deleted_event = SowEventActions(farm=farm).delete_event(event.id)

    assert deleted_event.sow_id == sow.id
    assert deleted_event.model_label == "sows.SowEventModel"
    assert deleted_event.object_id == event.id
    assert "INSEMINATION" in deleted_event.object_repr
    assert not SowEventModel.objects.filter(id=event.id).exists()


@pytest.mark.django_db
def test_delete_event_rejects_event_from_other_farm(farm):
    other_user = User.objects.create_user(username="sow-action-delete-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_sow = SowModel.objects.create(ear_tag="DELETE-ACTION-FOREIGN", farm=other_farm)
    foreign_event = SowEventModel.objects.create(
        sow=foreign_sow,
        event_type="INSEMINATION",
        event_date=date(2026, 7, 1),
        details={"technician": "Jan"},
    )

    with pytest.raises(Http404):
        SowEventActions(farm=farm).delete_event(foreign_event.id)

    assert SowEventModel.objects.filter(id=foreign_event.id).exists()


@pytest.mark.django_db
def test_bulk_create_events_rolls_back_when_row_sow_is_outside_farm(farm):
    own_sow = SowModel.objects.create(ear_tag="BULK-ACTION-OWN", farm=farm)
    other_user = User.objects.create_user(username="sow-action-bulk-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_sow = SowModel.objects.create(ear_tag="BULK-ACTION-FOREIGN", farm=other_farm)

    rows = [
        SimpleNamespace(
            sow=own_sow,
            event_type="INSEMINATION",
            event_date=date(2026, 7, 1),
            details={"technician": "Jan"},
        ),
        SimpleNamespace(
            sow=foreign_sow,
            event_type="INSEMINATION",
            event_date=date(2026, 7, 1),
            details={"technician": "Jan"},
        ),
    ]

    with pytest.raises(Http404):
        SowEventActions(farm=farm).bulk_create_events(rows)

    assert not SowEventModel.objects.filter(sow=own_sow).exists()
    assert not SowEventModel.objects.filter(sow=foreign_sow).exists()
