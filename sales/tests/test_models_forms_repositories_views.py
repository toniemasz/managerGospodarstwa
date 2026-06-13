from datetime import date
from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from sales.forms import PigSaleForm
from sales.models import PigSaleModel
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
