from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_piglet_transfer_migration_preserves_existing_reproduction_data():
    executor = MigrationExecutor(connection)
    old_target = [("sows", "0011_mortality_types_and_constraints")]
    new_target = [("sows", "0012_piglettransfermodel_and_more")]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model("auth", "User")
    Farm = old_apps.get_model("farms", "FarmModel")
    Sow = old_apps.get_model("sows", "SowModel")
    Event = old_apps.get_model("sows", "SowEventModel")
    Mortality = old_apps.get_model("sows", "MortalityReportModel")

    owner = User.objects.create(username="piglet-migration-owner")
    farm = Farm.objects.create(owner=owner, name="Migracja odchowu")
    sow = Sow.objects.create(farm=farm, ear_tag="HISTORY-1", entry_date=date(2020, 1, 1))
    farrowing = Event.objects.create(
        sow=sow,
        event_type="FARROWING",
        event_date=date(2025, 1, 1),
        details={"born_alive": 8, "born_dead": 1},
    )
    weaning = Event.objects.create(
        sow=sow,
        event_type="WEANING",
        event_date=date(2025, 1, 28),
        details={"count": 10},
    )
    mortality = Mortality.objects.create(
        farm=farm,
        mortality_type="PROSIAK",
        mortality_date=date(2025, 2, 1),
        quantity=2,
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewEvent = new_apps.get_model("sows", "SowEventModel")
    NewMortality = new_apps.get_model("sows", "MortalityReportModel")
    Transfer = new_apps.get_model("sows", "PigletTransferModel")

    assert NewEvent.objects.get(pk=farrowing.pk).details == {"born_alive": 8, "born_dead": 1}
    assert NewEvent.objects.get(pk=weaning.pk).details == {"count": 10}
    migrated_mortality = NewMortality.objects.get(pk=mortality.pk)
    assert migrated_mortality.quantity == 2
    assert migrated_mortality.farrowing_id is None
    assert Transfer.objects.count() == 0

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
