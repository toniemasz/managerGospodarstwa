from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from farms.models import AuditLogModel
from sales.forms import PigSaleForm, SaleClassRowForm, SaleClassRowFormSet
from sales.models import PigSaleModel, SaleClassRowModel
from sales.services.sale_form_service import SaleFormService
from sales.services.sale_repository import SaleRepository
from farms.services.farm_service import get_or_create_user_farm


@pytest.fixture
def auth_client(client):
    user = User.objects.create_user(username='sales-user', password='password')
    client.user = user
    client.farm = get_or_create_user_farm(user)
    client.login(username='sales-user', password='password')
    return client


@pytest.mark.django_db
def test_sale_model_form_repository_and_admin_registration():
    sale = PigSaleModel.objects.create(
        sale_date=date(2026, 6, 1),
        quantity=10,
        total_weight=Decimal('950.50'),
        meat_class='E',
        price_per_kg=Decimal('8.20'),
    )

    form = PigSaleForm(data={
        'sale_date': '2026-06-02',
        'meat_class': 'U',
        'quantity': 5,
        'total_weight': '500.00',
        'price_per_kg': '7.50',
    })
    repo = SaleRepository()

    assert str(sale) == "Sprzedaż 10 szt. - 2026-06-01"
    assert form.is_valid() is True
    assert repo.get_all_sales()[0].id == sale.id
    assert repo.get_sale_by_id(sale.id).total_price == Decimal('7794.1000')
    assert PigSaleModel in admin.site._registry


@pytest.mark.django_db
def test_sales_views_require_login_and_handle_create(auth_client, client):
    assert Client().get(reverse('sales_list')).status_code == 302

    list_response = auth_client.get(reverse('sales_list'))
    assert list_response.status_code == 200
    assert 'sales/sales_list.html' in [t.name for t in list_response.templates]

    add_response = auth_client.get(reverse('add_sale'))
    assert add_response.status_code == 200
    assert 'sales/add_sale.html' in [t.name for t in add_response.templates]

    post_response = auth_client.post(reverse('add_sale'), {
        'sale_date': '2026-06-03',
        'meat_class': 'R',
        'quantity': 8,
        'total_weight': '760.00',
        'price_per_kg': '7.80',
    })

    assert post_response.status_code == 302
    assert PigSaleModel.objects.filter(quantity=8, meat_class='R', farm=auth_client.farm).exists()
    sale = PigSaleModel.objects.get(quantity=8, meat_class='R', farm=auth_client.farm)
    assert AuditLogModel.objects.filter(farm=auth_client.farm, action="CREATE", object_id=str(sale.pk)).exists()


@pytest.mark.django_db
def test_sales_list_displays_net_values(auth_client):
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date.today(),
        quantity=10,
        total_weight=Decimal('1000.00'),
        price_per_kg=Decimal('8.00'),
        net_value=Decimal('8000.00'),
        gross_value=Decimal('8640.00'),
    )

    response = auth_client.get(reverse('sales_list'), {'period': 'all'})
    content = response.content.decode()

    assert response.status_code == 200
    assert 'Przychód netto' in content
    assert '>Netto<' in content
    assert '8 000' in content
    assert '8 640' in content
    assert '8\xa0000,00' not in content
    assert '8\xa0640,00' not in content


@pytest.mark.django_db
def test_sales_list_displays_large_mass_in_tonnes(auth_client):
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date.today(),
        quantity=10,
        total_weight=Decimal('1250.00'),
        live_weight=Decimal('1500.00'),
    )

    content = auth_client.get(reverse('sales_list'), {'period': 'all'}).content.decode()

    assert '1,25 t' in content
    assert '1,5 t' in content


@pytest.mark.django_db
def test_delete_sale_view_removes_sale(auth_client):
    sale = PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 6, 4),
        quantity=3,
        total_weight=Decimal('300.00'),
        meat_class='E',
        price_per_kg=Decimal('8.00'),
    )

    response = auth_client.post(reverse('delete_sale', args=[sale.id]))

    assert response.status_code == 302
    assert not PigSaleModel.objects.filter(id=sale.id).exists()
    assert AuditLogModel.objects.filter(farm=auth_client.farm, action="DELETE", object_id=str(sale.id)).exists()


@pytest.mark.django_db
def test_delete_sale_view_is_scoped_to_current_farm(auth_client):
    other_user = User.objects.create_user(username='sales-delete-other')
    other_farm = get_or_create_user_farm(other_user)
    foreign_sale = PigSaleModel.objects.create(
        farm=other_farm,
        sale_date=date(2026, 6, 4),
        quantity=3,
        total_weight=Decimal('300.00'),
        meat_class='E',
        price_per_kg=Decimal('8.00'),
    )

    response = auth_client.post(reverse('delete_sale', args=[foreign_sale.id]))

    assert response.status_code == 404
    assert PigSaleModel.objects.filter(id=foreign_sale.id, farm=other_farm).exists()
    assert not AuditLogModel.objects.filter(farm=auth_client.farm, action="DELETE").exists()


@pytest.mark.django_db
def test_sale_repository_filters_data_by_farm():
    user = User.objects.create_user(username='sale-owner')
    other_user = User.objects.create_user(username='sale-other')
    farm = get_or_create_user_farm(user)
    other_farm = get_or_create_user_farm(other_user)

    own_sale = PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 6, 1),
        quantity=10,
        total_weight=Decimal('950.50'),
        meat_class='E',
        price_per_kg=Decimal('8.20'),
    )
    PigSaleModel.objects.create(
        farm=other_farm,
        sale_date=date(2026, 6, 2),
        quantity=99,
        total_weight=Decimal('1000.00'),
        meat_class='U',
        price_per_kg=Decimal('7.20'),
    )

    sales = SaleRepository(farm=farm).get_all_sales()

    assert [sale.id for sale in sales] == [own_sale.id]


@pytest.mark.django_db
def test_sale_repository_filters_sales_between_dates():
    user = User.objects.create_user(username='sale-date-owner')
    farm = get_or_create_user_farm(user)
    in_range = PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 6, 10),
        quantity=10,
        total_weight=Decimal('900.00'),
        meat_class='E',
        price_per_kg=Decimal('8.00'),
    )
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 5, 10),
        quantity=5,
        total_weight=Decimal('450.00'),
        meat_class='U',
        price_per_kg=Decimal('7.00'),
    )

    sales = SaleRepository(farm=farm).get_sales_between(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    assert [sale.id for sale in sales] == [in_range.id]


@pytest.mark.django_db
def test_sales_year_filter_and_document_number_uniqueness_per_year(auth_client):
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2025, 5, 1),
        document_number="FV/1",
        quantity=5,
        net_value=Decimal("5000"),
    )
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 5, 1),
        document_number="FV/2",
        quantity=6,
        net_value=Decimal("6000"),
    )

    response = auth_client.get(reverse("sales_list"), {"year": 2025})
    content = response.content.decode()
    assert "FV/1" in content
    assert "FV/2" not in content
    assert response.context["selected_year"] == 2025

    same_year = PigSaleForm(
        data={"sale_date": "2025-08-01", "document_number": "fv/1"},
        instance=PigSaleModel(farm=auth_client.farm),
        farm=auth_client.farm,
    )
    other_year = PigSaleForm(
        data={"sale_date": "2026-08-01", "document_number": "FV/1"},
        instance=PigSaleModel(farm=auth_client.farm),
        farm=auth_client.farm,
    )
    assert not same_year.is_valid()
    assert other_year.is_valid()


@pytest.mark.django_db
def test_sales_list_filters_by_explicit_date_range(auth_client):
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 5, 1),
        document_number="MAY",
        quantity=5,
        net_value=Decimal("5000"),
    )
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 6, 1),
        document_number="JUNE",
        quantity=6,
        net_value=Decimal("6000"),
    )
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 7, 1),
        document_number="JULY",
        quantity=7,
        net_value=Decimal("7000"),
    )

    response = auth_client.get(reverse("sales_list"), {
        "year": "2026",
        "date_from": "2026-06-01",
        "date_to": "2026-06-30",
    })

    assert response.status_code == 200
    assert [sale.document_number for sale in response.context["sales"]] == ["JUNE"]
    assert response.context["date_from"] == date(2026, 6, 1)
    assert response.context["date_to"] == date(2026, 6, 30)


@pytest.mark.django_db
def test_sales_list_swaps_reversed_date_range(auth_client):
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 6, 1),
        document_number="JUNE",
        quantity=6,
        net_value=Decimal("6000"),
    )
    PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 8, 1),
        document_number="AUGUST",
        quantity=8,
        net_value=Decimal("8000"),
    )

    response = auth_client.get(reverse("sales_list"), {
        "year": "2026",
        "date_from": "2026-07-31",
        "date_to": "2026-06-01",
    })

    assert response.status_code == 200
    assert [sale.document_number for sale in response.context["sales"]] == ["JUNE"]
    assert response.context["date_from"] == date(2026, 6, 1)
    assert response.context["date_to"] == date(2026, 7, 31)


@pytest.mark.django_db
def test_sale_form_service_rolls_back_rows_when_new_rows_fail(auth_client):
    sale = PigSaleModel.objects.create(
        farm=auth_client.farm,
        sale_date=date(2026, 6, 4),
        quantity=3,
        total_weight=Decimal('300.00'),
        meat_class='E',
        price_per_kg=Decimal('8.00'),
    )
    old_row = SaleClassRowModel.objects.create(
        sale=sale,
        line_no=1,
        meat_class='E',
        quantity=3,
        weight=Decimal('300.00'),
        price_per_kg=Decimal('8.00'),
        gross_value=Decimal('2400.00'),
    )
    form = PigSaleForm(data={
        'sale_date': '2026-06-05',
        'document_number': 'FV/1',
        'tattoo': 'ABC',
    }, instance=sale)
    formset = SaleClassRowFormSet(data={
        'rows-TOTAL_FORMS': '1',
        'rows-INITIAL_FORMS': '0',
        'rows-MIN_NUM_FORMS': '0',
        'rows-MAX_NUM_FORMS': '1000',
        'rows-0-line_no': '1',
        'rows-0-meat_class': 'U',
        'rows-0-quantity': '4',
        'rows-0-weight': '400.00',
        'rows-0-price_per_kg': '7.50',
        'rows-0-gross_value': '3000.00',
    }, prefix='rows')

    assert form.is_valid() is True
    assert formset.is_valid() is True

    with patch('sales.services.sale_form_service.SaleClassRowModel.objects.bulk_create', side_effect=RuntimeError):
        with pytest.raises(RuntimeError):
            SaleFormService(farm=auth_client.farm).save_sale(form, formset, sale)

    assert SaleClassRowModel.objects.filter(id=old_row.id, sale=sale).exists()
    sale.refresh_from_db()
    assert sale.sale_date == date(2026, 6, 4)
def test_sale_mass_forms_convert_selected_tonnes_to_kilograms():
    sale_form = PigSaleForm(data={
        "sale_date": "2026-07-11",
        "document_number": "",
        "tattoo": "",
        "live_weight": "1,25",
        "live_weight_unit": "t",
    })
    row_form = SaleClassRowForm(data={
        "line_no": "1",
        "weight": "1,5",
        "weight_unit": "t",
        "avg_weight": "0,12",
        "avg_weight_unit": "t",
    })

    assert sale_form.is_valid(), sale_form.errors
    assert row_form.is_valid(), row_form.errors
    assert sale_form.cleaned_data["live_weight"] == Decimal("1250.00")
    assert row_form.cleaned_data["weight"] == Decimal("1500.00")
    assert row_form.cleaned_data["avg_weight"] == Decimal("120.00")
