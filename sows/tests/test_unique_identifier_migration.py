from datetime import date

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_migration_suffixes_active_sow_and_plan_conflicts_without_linking_history():
    executor = MigrationExecutor(connection)
    old_target = [('sows', '0012_piglettransfermodel_and_more')]
    new_target = [('sows', '0013_normalized_business_identifiers')]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model('auth', 'User')
    Farm = old_apps.get_model('farms', 'FarmModel')
    Sow = old_apps.get_model('sows', 'SowModel')
    Event = old_apps.get_model('sows', 'SowEventModel')
    Plan = old_apps.get_model('sows', 'VaccinationPlanModel')

    owner = User.objects.create(username='identifier-migration-owner')
    other_owner = User.objects.create(username='identifier-migration-other')
    farm = Farm.objects.create(owner=owner, name='Migracja identyfikatorów')
    other_farm = Farm.objects.create(owner=other_owner, name='Inne gospodarstwo')

    first = Sow.objects.create(farm=farm, ear_tag='85762', entry_date=date(2025, 10, 1))
    second = Sow.objects.create(farm=farm, ear_tag=' 85762 ', entry_date=date(2025, 10, 1))
    archived = Sow.objects.create(
        farm=farm,
        ear_tag='85762',
        entry_date=date(2020, 1, 1),
        is_archived=True,
    )
    Event.objects.create(sow=first, event_type='INSEMINATION', event_date=date(2026, 1, 1))
    Event.objects.create(sow=second, event_type='FARROWING', event_date=date(2026, 2, 1))
    Plan.objects.create(farm=farm, name='Parwo')
    Plan.objects.create(farm=farm, name=' parwo ')
    Sow.objects.create(farm=other_farm, ear_tag='85762')

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewSow = new_apps.get_model('sows', 'SowModel')
    NewEvent = new_apps.get_model('sows', 'SowEventModel')
    NewPlan = new_apps.get_model('sows', 'VaccinationPlanModel')

    assert NewSow.objects.get(pk=first.pk).ear_tag == '85762'
    assert NewSow.objects.get(pk=second.pk).ear_tag == '85762 (1)'
    assert NewSow.objects.get(pk=archived.pk).ear_tag == '85762'
    assert NewEvent.objects.get(sow_id=first.pk).event_type == 'INSEMINATION'
    assert NewEvent.objects.get(sow_id=second.pk).event_type == 'FARROWING'
    assert list(NewPlan.objects.filter(farm_id=farm.pk).values_list('name', flat=True)) == [
        'Parwo',
        'parwo (1)',
    ]

    with pytest.raises(IntegrityError), transaction.atomic():
        NewSow.objects.create(farm_id=farm.pk, ear_tag=' 85762 ')

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
