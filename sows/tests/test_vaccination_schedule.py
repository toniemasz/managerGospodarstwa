from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import Http404

from farms.services.farm_service import get_or_create_user_farm
from sows.actions.vaccinations import VaccinationActions
from sows.actions.events import SowEventActions
from sows.domain.vaccinations import (
    add_vaccination_interval,
    first_vaccination_date_on_or_after,
    vaccination_cycle_id,
)
from sows.models import (
    SowEventModel,
    SowModel,
    VaccinationCycleModel,
    VaccinationPlanModel,
)
from sows.services.sow_repository import SowRepository
from sows.services.vaccination_schedule import VaccinationScheduleService


@pytest.fixture
def farm(db):
    return get_or_create_user_farm(User.objects.create_user(username="vaccination-schedule"))


def create_plan(farm, **overrides):
    values = {
        "name": "Różyca",
        "interval_value": 1,
        "interval_unit": VaccinationPlanModel.INTERVAL_MONTHS,
        "schedule_mode": VaccinationPlanModel.SCHEDULE_FIXED,
        "first_due_date": date(2024, 1, 31),
        "scope": VaccinationPlanModel.SCOPE_ALL,
        "reminder_days_ahead": 30,
        "is_active": True,
    }
    values.update(overrides)
    return VaccinationPlanModel.objects.create(farm=farm, **values)


def reminders(farm, current_date):
    sows = SowRepository(farm).get_all_sows()
    return VaccinationScheduleService(farm).build_reminders(sows, current_date)


@pytest.mark.parametrize(
    ("base_date", "value", "unit", "expected"),
    [
        (date(2024, 1, 1), 14, "DAYS", date(2024, 1, 15)),
        (date(2024, 1, 1), 6, "WEEKS", date(2024, 2, 12)),
        (date(2024, 1, 31), 1, "MONTHS", date(2024, 2, 29)),
        (date(2023, 1, 31), 1, "MONTHS", date(2023, 2, 28)),
        (date(2024, 2, 29), 1, "YEARS", date(2025, 2, 28)),
    ],
)
def test_add_vaccination_interval_uses_calendar_units(base_date, value, unit, expected):
    assert add_vaccination_interval(base_date, value, unit) == expected


def test_old_periodic_date_is_advanced_without_year_by_year_iteration():
    assert first_vaccination_date_on_or_after(
        date(1900, 1, 31),
        date(2026, 7, 28),
        1,
        VaccinationPlanModel.INTERVAL_MONTHS,
    ) == date(2026, 7, 28)


@pytest.mark.django_db
def test_periodic_plan_never_falls_back_to_entry_or_current_date(farm):
    SowModel.objects.create(farm=farm, ear_tag="NO-FALLBACK", entry_date=date(2020, 1, 1))
    create_plan(farm, first_due_date=None)

    assert reminders(farm, date(2026, 7, 12)) == []


@pytest.mark.django_db
def test_fixed_schedule_does_not_move_after_late_completion(farm):
    sow = SowModel.objects.create(farm=farm, ear_tag="FIXED")
    plan = create_plan(farm)
    first_cycle = vaccination_cycle_id(plan.id, date(2024, 1, 31))
    VaccinationCycleModel.objects.create(
        plan=plan,
        sow=sow,
        cycle_id=first_cycle,
        scheduled_date=date(2024, 1, 31),
        status=VaccinationCycleModel.STATUS_COMPLETED,
        completed_at=date(2024, 2, 10),
    )

    item = reminders(farm, date(2024, 2, 15))[0]

    assert item["target_date"] == date(2024, 2, 29)


@pytest.mark.django_db
def test_from_last_completed_uses_actual_completion_but_skip_uses_scheduled_date(farm):
    sow = SowModel.objects.create(farm=farm, ear_tag="ROLLING")
    plan = create_plan(
        farm,
        schedule_mode=VaccinationPlanModel.SCHEDULE_FROM_LAST_COMPLETED,
        first_due_date=date(2024, 1, 31),
    )
    VaccinationCycleModel.objects.create(
        plan=plan,
        sow=sow,
        cycle_id=vaccination_cycle_id(plan.id, date(2024, 1, 31)),
        scheduled_date=date(2024, 1, 31),
        status=VaccinationCycleModel.STATUS_COMPLETED,
        completed_at=date(2024, 2, 10),
    )
    VaccinationCycleModel.objects.create(
        plan=plan,
        sow=sow,
        cycle_id=vaccination_cycle_id(plan.id, date(2024, 3, 10)),
        scheduled_date=date(2024, 3, 10),
        status=VaccinationCycleModel.STATUS_SKIPPED,
        skipped_at=date(2024, 3, 20),
    )

    item = reminders(farm, date(2024, 4, 1))[0]

    assert item["target_date"] == date(2024, 4, 10)


@pytest.mark.django_db
def test_overdue_cycle_remains_visible_until_closed(farm):
    SowModel.objects.create(farm=farm, ear_tag="OVERDUE")
    create_plan(farm, first_due_date=date(2024, 1, 1), reminder_days_ahead=7)

    item = reminders(farm, date(2024, 3, 1))[0]

    assert item["target_date"] == date(2024, 1, 1)
    assert item["status"] == "overdue"
    assert item["status_label"] == "Zaległe"


@pytest.mark.django_db
def test_periodic_plan_ignores_pre_start_cycles_but_keeps_real_overdue(farm):
    SowModel.objects.create(
        farm=farm,
        ear_tag="START-PERIODIC",
        entry_date=date(2026, 1, 1),
    )
    create_plan(
        farm,
        first_due_date=date(2026, 7, 10),
        starts_on=date(2026, 7, 28),
        interval_value=10,
        interval_unit=VaccinationPlanModel.INTERVAL_DAYS,
        reminder_days_ahead=7,
    )

    before_due = reminders(farm, date(2026, 7, 28))[0]
    overdue = reminders(farm, date(2026, 8, 5))[0]

    assert before_due["target_date"] == date(2026, 7, 30)
    assert before_due["status"] == "upcoming"
    assert overdue["target_date"] == date(2026, 7, 30)
    assert overdue["status"] == "overdue"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("event_type", "event_date", "plan_values"),
    [
        (
            "INSEMINATION",
            date(2026, 7, 1),
            {"days_after_event": 10, "event_source": "INSEMINATION"},
        ),
        (
            "FARROWING",
            date(2026, 7, 1),
            {"days_after_event": 10, "event_source": "FARROWING"},
        ),
    ],
)
def test_after_event_plan_does_not_restore_pre_start_due_date(
    farm,
    event_type,
    event_date,
    plan_values,
):
    sow = SowModel.objects.create(
        farm=farm,
        ear_tag=f"OLD-{event_type}",
        entry_date=date(2026, 1, 1),
    )
    SowEventModel.objects.create(
        sow=sow,
        event_type=event_type,
        event_date=event_date,
    )
    create_plan(
        farm,
        interval_value=None,
        interval_unit=None,
        schedule_mode=None,
        first_due_date=None,
        starts_on=date(2026, 7, 28),
        **plan_values,
    )

    assert reminders(farm, date(2026, 8, 5)) == []
    assert not VaccinationCycleModel.objects.exists()
    assert not SowEventModel.objects.filter(event_type="VACCINATION").exists()


@pytest.mark.django_db
def test_old_event_can_generate_due_date_on_or_after_plan_start(farm):
    sow = SowModel.objects.create(
        farm=farm,
        ear_tag="FUTURE-FROM-OLD",
        entry_date=date(2026, 1, 1),
    )
    SowEventModel.objects.create(
        sow=sow,
        event_type="INSEMINATION",
        event_date=date(2026, 7, 20),
    )
    create_plan(
        farm,
        interval_value=None,
        interval_unit=None,
        schedule_mode=None,
        first_due_date=None,
        starts_on=date(2026, 7, 28),
        days_after_event=16,
        event_source="INSEMINATION",
        reminder_days_ahead=10,
    )

    item = reminders(farm, date(2026, 7, 28))[0]

    assert item["target_date"] == date(2026, 8, 5)


@pytest.mark.django_db
def test_before_farrowing_plan_ignores_due_date_before_start(farm):
    sow = SowModel.objects.create(
        farm=farm,
        ear_tag="BEFORE-FARROWING-START",
        entry_date=date(2026, 1, 1),
    )
    SowEventModel.objects.create(
        sow=sow,
        event_type="INSEMINATION",
        event_date=date(2026, 4, 20),
    )
    SowEventModel.objects.create(
        sow=sow,
        event_type="PREGNANCY_CHECK",
        event_date=date(2026, 5, 20),
        details={"result": "TAK"},
    )
    create_plan(
        farm,
        interval_value=None,
        interval_unit=None,
        schedule_mode=None,
        first_due_date=None,
        starts_on=date(2026, 7, 28),
        days_before_farrowing=21,
    )

    assert reminders(farm, date(2026, 8, 1)) == []


@pytest.mark.django_db
def test_scope_selected_and_exclusion_are_respected(farm):
    selected = SowModel.objects.create(farm=farm, ear_tag="SELECTED")
    other = SowModel.objects.create(farm=farm, ear_tag="OTHER")
    plan = create_plan(
        farm,
        first_due_date=date(2024, 1, 1),
        scope=VaccinationPlanModel.SCOPE_SELECTED,
    )
    plan.selected_sows.add(selected)

    assert [item["sow_id"] for item in reminders(farm, date(2024, 1, 1))] == [selected.id]

    plan.scope = VaccinationPlanModel.SCOPE_ALL
    plan.save(update_fields=("scope",))
    plan.excluded_sows.add(selected)

    assert [item["sow_id"] for item in reminders(farm, date(2024, 1, 1))] == [other.id]


@pytest.mark.django_db
def test_all_scope_includes_sow_added_after_plan(farm):
    create_plan(farm, first_due_date=date(2024, 1, 1))
    later_sow = SowModel.objects.create(farm=farm, ear_tag="LATER", entry_date=date(2025, 1, 1))

    assert reminders(farm, date(2025, 1, 1))[0]["sow_id"] == later_sow.id


@pytest.mark.django_db
def test_recording_cycle_writes_snapshot_and_blocks_duplicate(farm):
    today = date.today()
    sow = SowModel.objects.create(farm=farm, ear_tag="RECORD")
    plan = create_plan(farm, first_due_date=today)
    cycle_id = vaccination_cycle_id(plan.id, today)

    with patch("sows.actions.vaccinations.invalidate_farm_cache_on_commit") as invalidate:
        events = VaccinationActions(farm).record_many(
            plan_id=plan.id,
            sow_ids=[sow.id],
            cycle_id=cycle_id,
            scheduled_date=today,
        )
        invalidate.assert_called_once_with(farm, groups=("sows",))

    event = events[0]
    assert event.vaccination_plan == plan
    assert event.vaccine_name == plan.name
    assert event.scheduled_date == today
    assert event.details["vaccination_plan_id"] == plan.id
    assert VaccinationCycleModel.objects.filter(status="COMPLETED").count() == 1

    with pytest.raises(ValidationError):
        VaccinationActions(farm).record_many(
            plan_id=plan.id,
            sow_ids=[sow.id],
            cycle_id=cycle_id,
            scheduled_date=today,
        )
    assert SowEventModel.objects.filter(sow=sow, event_type="VACCINATION").count() == 1


@pytest.mark.django_db
def test_skip_closes_only_current_cycle_and_next_date_ignores_click_date(farm):
    today = date.today()
    sow = SowModel.objects.create(farm=farm, ear_tag="SKIP")
    plan = create_plan(
        farm,
        first_due_date=today - timedelta(days=10),
        reminder_days_ahead=60,
        schedule_mode=VaccinationPlanModel.SCHEDULE_FROM_LAST_COMPLETED,
    )
    scheduled = today - timedelta(days=10)
    cycle_id = vaccination_cycle_id(plan.id, scheduled)

    VaccinationActions(farm).skip_cycle(
        plan_id=plan.id,
        sow_id=sow.id,
        cycle_id=cycle_id,
        scheduled_date=scheduled,
        skipped_date=today,
        note="Brak preparatu",
    )

    item = reminders(farm, today)[0]
    assert item["target_date"] == add_vaccination_interval(scheduled, 1, "MONTHS")
    state = VaccinationCycleModel.objects.get()
    assert state.status == "SKIPPED"
    assert state.note == "Brak preparatu"


@pytest.mark.django_db
def test_excluding_one_sow_and_deactivating_plan_preserve_history(farm):
    today = date.today()
    sow = SowModel.objects.create(farm=farm, ear_tag="HISTORY")
    plan = create_plan(farm, first_due_date=today)
    cycle_id = vaccination_cycle_id(plan.id, today)
    event = VaccinationActions(farm).record_many(
        plan_id=plan.id,
        sow_ids=[sow.id],
        cycle_id=cycle_id,
        scheduled_date=today,
    )[0]

    VaccinationActions(farm).exclude_sow(plan_id=plan.id, sow_id=sow.id)
    assert plan.excluded_sows.filter(id=sow.id).exists()

    VaccinationActions(farm).deactivate_plan(plan_id=plan.id)
    plan.refresh_from_db()
    event.refresh_from_db()
    assert plan.is_active is False
    assert not plan.selected_sows.exists()
    assert not plan.excluded_sows.exists()
    assert event.vaccine_name == "Różyca"
    assert event.vaccination_plan == plan
    assert VaccinationCycleModel.objects.filter(plan=plan, sow=sow).exists()


@pytest.mark.django_db
def test_actions_reject_objects_from_other_farm(farm):
    other_farm = get_or_create_user_farm(User.objects.create_user(username="vaccination-other-farm"))
    foreign_sow = SowModel.objects.create(farm=other_farm, ear_tag="FOREIGN")
    plan = create_plan(farm, first_due_date=date.today())

    with pytest.raises(Http404):
        VaccinationActions(farm).record_many(
            plan_id=plan.id,
            sow_ids=[foreign_sow.id],
            cycle_id=vaccination_cycle_id(plan.id, date.today()),
            scheduled_date=date.today(),
        )


@pytest.mark.django_db
def test_deleting_completed_vaccination_reopens_its_cycle(farm):
    today = date.today()
    sow = SowModel.objects.create(farm=farm, ear_tag="DELETE-CYCLE")
    plan = create_plan(farm, first_due_date=today)
    cycle_id = vaccination_cycle_id(plan.id, today)
    event = VaccinationActions(farm).record_many(
        plan_id=plan.id,
        sow_ids=[sow.id],
        cycle_id=cycle_id,
        scheduled_date=today,
    )[0]

    SowEventActions(farm).delete_event(event.id)

    assert not VaccinationCycleModel.objects.filter(plan=plan, sow=sow).exists()
    assert reminders(farm, today)[0]["cycle_id"] == cycle_id


@pytest.mark.django_db
def test_schedule_query_count_does_not_grow_with_number_of_sows(farm, django_assert_num_queries):
    create_plan(farm, first_due_date=date.today())
    SowModel.objects.bulk_create([
        SowModel(farm=farm, ear_tag=f"QUERY-{index:02d}")
        for index in range(20)
    ])
    sow_entities = SowRepository(farm).get_all_sows()

    with django_assert_num_queries(4):
        result = VaccinationScheduleService(farm).build_reminders(sow_entities, date.today())

    assert len(result) == 20
