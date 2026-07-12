from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_vaccination_data_is_preserved_and_safely_backfilled():
    executor = MigrationExecutor(connection)
    old_target = [("sows", "0007_mortality_reports_and_miscarriage")]
    new_target = [("sows", "0010_vaccination_cycle_constraints")]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model("auth", "User")
    Farm = old_apps.get_model("farms", "FarmModel")
    Plan = old_apps.get_model("sows", "VaccinationPlanModel")
    Sow = old_apps.get_model("sows", "SowModel")
    Event = old_apps.get_model("sows", "SowEventModel")

    owner = User.objects.create(username="migration-owner")
    other_owner = User.objects.create(username="migration-other")
    farm = Farm.objects.create(owner=owner, name="Migracja")
    other_farm = Farm.objects.create(owner=other_owner, name="Inne")
    matched_plan = Plan.objects.create(farm=farm, name="Parwo", interval_months=4, reminder_days_ahead=9)
    no_history_plan = Plan.objects.create(farm=farm, name="Bez historii", interval_months=2)
    Plan.objects.create(farm=farm, name="DUBLET", interval_months=1)
    Plan.objects.create(farm=farm, name="dublet", interval_months=1)
    foreign_plan = Plan.objects.create(farm=other_farm, name="Parwo", interval_months=6)
    sow = Sow.objects.create(farm=farm, ear_tag="OLD-1", entry_date=date(2020, 1, 1))
    other_sow = Sow.objects.create(farm=other_farm, ear_tag="OTHER-1", entry_date=date(2020, 1, 1))
    matched_event = Event.objects.create(
        sow=sow,
        event_type="VACCINATION",
        event_date=date(2023, 5, 17),
        details={"vaccine_name": "Parwo", "cycle_id": "cyclic_2023-05-15"},
    )
    ambiguous_event = Event.objects.create(
        sow=sow,
        event_type="VACCINATION",
        event_date=date(2023, 6, 1),
        details={"vaccine_name": "DuBlEt"},
    )
    legacy_event = Event.objects.create(
        sow=sow,
        event_type="VACCINATION",
        event_date=date(2022, 1, 2),
        details={"vaccine_name": "Historyczne bez planu"},
    )
    foreign_event = Event.objects.create(
        sow=other_sow,
        event_type="VACCINATION",
        event_date=date(2023, 5, 17),
        details={"vaccine_name": "Parwo", "cycle_id": "foreign-cycle"},
    )
    old_plan_count = Plan.objects.count()
    old_event_count = Event.objects.filter(event_type="VACCINATION").count()

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewPlan = new_apps.get_model("sows", "VaccinationPlanModel")
    NewEvent = new_apps.get_model("sows", "SowEventModel")
    Cycle = new_apps.get_model("sows", "VaccinationCycleModel")

    assert NewPlan.objects.count() == old_plan_count
    assert NewEvent.objects.filter(event_type="VACCINATION").count() == old_event_count

    migrated_plan = NewPlan.objects.get(id=matched_plan.id)
    assert migrated_plan.interval_value == 4
    assert migrated_plan.interval_unit == "MONTHS"
    assert migrated_plan.schedule_mode == "FROM_LAST_COMPLETED"
    assert migrated_plan.reminder_days_ahead == 9
    assert migrated_plan.is_active is True

    migrated_no_history = NewPlan.objects.get(id=no_history_plan.id)
    assert migrated_no_history.is_active is False
    assert migrated_no_history.requires_configuration is True
    assert migrated_no_history.first_due_date is None

    migrated_event = NewEvent.objects.get(id=matched_event.id)
    assert migrated_event.event_date == date(2023, 5, 17)
    assert migrated_event.details == {"vaccine_name": "Parwo", "cycle_id": "cyclic_2023-05-15"}
    assert migrated_event.vaccine_name == "Parwo"
    assert migrated_event.vaccination_plan_id == matched_plan.id
    assert migrated_event.scheduled_date == date(2023, 5, 15)
    assert Cycle.objects.filter(
        plan_id=matched_plan.id,
        sow_id=sow.id,
        cycle_id="cyclic_2023-05-15",
        status="COMPLETED",
    ).exists()

    assert NewEvent.objects.get(id=ambiguous_event.id).vaccination_plan_id is None
    migrated_legacy = NewEvent.objects.get(id=legacy_event.id)
    assert migrated_legacy.vaccination_plan_id is None
    assert migrated_legacy.vaccine_name == "Historyczne bez planu"
    assert migrated_legacy.event_date == date(2022, 1, 2)
    assert NewEvent.objects.get(id=foreign_event.id).vaccination_plan_id == foreign_plan.id

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
