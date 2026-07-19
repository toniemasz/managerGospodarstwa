from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_sales_identifier_migration_suffixes_documents_per_year_and_renumbers_rows():
    executor = MigrationExecutor(connection)
    old_target = [('sales', '0005_require_farm')]
    new_target = [('sales', '0006_normalized_document_identifiers')]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model('auth', 'User')
    Farm = old_apps.get_model('farms', 'FarmModel')
    Sale = old_apps.get_model('sales', 'PigSaleModel')
    SaleRow = old_apps.get_model('sales', 'SaleClassRowModel')

    owner = User.objects.create(username='sale-identifier-migration')
    farm = Farm.objects.create(owner=owner, name='Migracja sprzedaży')
    first = Sale.objects.create(
        farm=farm,
        sale_date=date(2026, 1, 1),
        document_number='FV/1',
    )
    second = Sale.objects.create(
        farm=farm,
        sale_date=date(2026, 6, 1),
        document_number=' fv/1 ',
    )
    next_year = Sale.objects.create(
        farm=farm,
        sale_date=date(2027, 1, 1),
        document_number='FV/1',
    )
    SaleRow.objects.create(sale=first, line_no=1)
    SaleRow.objects.create(sale=first, line_no=1)

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewSale = new_apps.get_model('sales', 'PigSaleModel')
    NewSaleRow = new_apps.get_model('sales', 'SaleClassRowModel')

    assert NewSale.objects.get(pk=first.pk).document_number == 'FV/1'
    assert NewSale.objects.get(pk=second.pk).document_number == 'fv/1 (1)'
    assert NewSale.objects.get(pk=next_year.pk).document_number == 'FV/1'
    assert set(NewSaleRow.objects.filter(sale_id=first.pk).values_list('line_no', flat=True)) == {1, 2}

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
