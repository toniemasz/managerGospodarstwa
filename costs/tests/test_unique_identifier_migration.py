import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_cost_category_migration_suffixes_normalized_name_conflicts():
    executor = MigrationExecutor(connection)
    old_target = [('costs', '0005_protect_production_cost')]
    new_target = [('costs', '0006_normalized_category_names')]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model('auth', 'User')
    Farm = old_apps.get_model('farms', 'FarmModel')
    Category = old_apps.get_model('costs', 'CostCategoryModel')

    owner = User.objects.create(username='cost-identifier-migration')
    farm = Farm.objects.create(owner=owner, name='Migracja kosztów')
    Category.objects.create(farm=farm, name='Paliwo')
    Category.objects.create(farm=farm, name=' paliwo ')

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewCategory = new_apps.get_model('costs', 'CostCategoryModel')

    assert list(NewCategory.objects.values_list('name', flat=True).order_by('id')) == [
        'Paliwo',
        'paliwo (1)',
    ]

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
