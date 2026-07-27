from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from costs.forms import CostForm
from costs.models import CostCategoryModel, CostModel
from costs.services import CostService
from costs.actions import sync_production_cost
from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from feed.models import ProductionModel, RecipeModel


@pytest.fixture
def cost_context(client):
    user = get_user_model().objects.create_user(username="cost-owner", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    return client, user, farm


@pytest.mark.django_db
def test_category_create_edit_and_deactivate_are_audited(cost_context):
    client, _user, farm = cost_context
    response = client.post(reverse("add_cost_category"), {"name": "Paliwo", "description": "Ciągniki"})
    category = CostCategoryModel.objects.get(farm=farm)
    assert response.status_code == 302

    client.post(reverse("edit_cost_category", args=[category.pk]), {"name": "Paliwo i oleje", "description": "Maszyny"})
    client.post(reverse("deactivate_cost_category", args=[category.pk]))
    category.refresh_from_db()

    assert category.name == "Paliwo i oleje"
    assert category.is_active is False
    assert list(AuditLogModel.objects.filter(farm=farm).values_list("action", flat=True)) == [
        "DEACTIVATE", "UPDATE", "CREATE"
    ]


@pytest.mark.django_db
def test_cost_create_edit_delete_form_and_audit(cost_context):
    client, user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    data = {
        "date": "2026-03-10",
        "amount": "450.50",
        "category": category.pk,
        "description": "Badanie stada",
        "document_number": "FV/3",
        "supplier": "Gabinet",
        "is_paid": "on",
    }
    response = client.post(reverse("add_cost"), data)
    cost = CostModel.objects.get(farm=farm)
    assert response.status_code == 302
    assert cost.created_by == user

    data.update({"amount": "500.00", "description": "Badanie i leki"})
    client.post(reverse("edit_cost", args=[cost.pk]), data)
    cost.refresh_from_db()
    assert cost.amount == Decimal("500.00")

    client.post(reverse("delete_cost", args=[cost.pk]))
    assert not CostModel.objects.filter(pk=cost.pk).exists()
    assert set(AuditLogModel.objects.filter(farm=farm).values_list("action", flat=True)) == {"CREATE", "UPDATE", "DELETE"}

    other_user = get_user_model().objects.create_user(username="cost-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_category = CostCategoryModel.objects.create(farm=other_farm, name="Obca")
    form = CostForm(data={**data, "category": foreign_category.pk}, farm=farm)
    assert not form.is_valid()


@pytest.mark.django_db
def test_cost_list_filters_summary_and_farm_isolation(cost_context):
    client, _user, farm = cost_context
    category_a = CostCategoryModel.objects.create(farm=farm, name="Energia")
    category_b = CostCategoryModel.objects.create(farm=farm, name="Transport")
    CostModel.objects.create(farm=farm, category=category_a, date=date(2026, 1, 2), amount=100, description="Prąd", is_paid=True)
    CostModel.objects.create(farm=farm, category=category_b, date=date(2026, 2, 2), amount=300, description="Przewóz", is_paid=False)
    CostModel.objects.create(farm=farm, category=category_a, date=date(2025, 1, 2), amount=900, description="Stary koszt")
    other_user = get_user_model().objects.create_user(username="hidden-cost")
    other_farm = get_or_create_user_farm(other_user)
    other_category = CostCategoryModel.objects.create(farm=other_farm, name="Sekret")
    CostModel.objects.create(farm=other_farm, category=other_category, date=date(2026, 1, 2), amount=9999, description="UKRYTY")

    response = client.get(reverse("cost_list"), {"year": 2026, "category": category_a.pk})
    content = response.content.decode()
    assert response.status_code == 200
    listed_descriptions = [cost.description for cost in response.context["costs"]]
    assert "Prąd" in content
    assert listed_descriptions == ["Prąd"]
    assert "UKRYTY" not in content
    assert response.context["summary"]["total"] == Decimal("100")

    summary = CostService.summarize(CostModel.objects.filter(farm=farm, date__year=2026))
    assert summary["paid"] == Decimal("100")
    assert summary["unpaid"] == Decimal("300")
    assert summary["largest_category"]["category__name"] == "Transport"


@pytest.mark.django_db
def test_empty_cost_list_has_clear_empty_state(cost_context):
    client, _user, _farm = cost_context
    response = client.get(reverse("cost_list"), {"year": 2026})
    assert "Brak kosztów" in response.content.decode()


@pytest.mark.django_db
def test_manual_cost_cannot_have_zero_amount(cost_context):
    _client, _user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Energia")
    form = CostForm(data={
        "date": "2026-03-10",
        "amount": "0.00",
        "category": category.pk,
        "description": "Nieprawidłowy koszt",
        "document_number": "",
        "supplier": "",
    }, farm=farm)

    assert not form.is_valid()
    assert "większa od zera" in form.errors["amount"][0]


@pytest.mark.django_db(transaction=True)
def test_historical_backfill_creates_cost_even_when_fifo_amount_is_zero(cost_context):
    _client, _user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Historyczna pasza bez ceny")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2025, 1, 1),
        quantity_kg=Decimal("1000.00"),
        status=ProductionModel.Statuses.QUEUED,
        feed_cost_total=Decimal("0.00"),
        feed_cost_is_partial=True,
    )
    ProductionModel.objects.filter(pk=production.pk).update(status=ProductionModel.Statuses.COMPLETED)

    migration = import_module("costs.migrations.0002_production_costs")
    migration.backfill_production_costs(django_apps, None)
    migration.backfill_production_costs(django_apps, None)
    format_migration = import_module("costs.migrations.0003_format_feed_cost_mass_units")
    format_migration.format_feed_cost_descriptions(django_apps, None)

    cost = CostModel.objects.get(production=production)
    assert cost.amount == Decimal("0.00")
    assert cost.category.name == "Pasza"
    assert "1 t" in cost.description
    assert CostModel.objects.filter(production=production).count() == 1


@pytest.mark.django_db
def test_production_cost_sync_is_idempotent_and_farm_scoped(cost_context):
    _client, user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Koszt jawny")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 4, 1),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.QUEUED,
    )
    ProductionModel.objects.filter(pk=production.pk).update(
        status=ProductionModel.Statuses.COMPLETED,
        feed_cost_total=Decimal("123.45"),
    )
    production.refresh_from_db()

    first = sync_production_cost(farm=farm, production=production, user=user)
    ProductionModel.objects.filter(pk=production.pk).update(feed_cost_total=Decimal("150.00"))
    production.refresh_from_db()
    second = sync_production_cost(farm=farm, production=production, user=user)

    assert first.pk == second.pk
    assert CostModel.objects.filter(production=production).count() == 1
    assert CostModel.objects.get(production=production).amount == Decimal("150.00")

    other_user = get_user_model().objects.create_user(username="foreign-cost-sync")
    other_farm = get_or_create_user_farm(other_user)
    with pytest.raises(ValidationError, match="innego gospodarstwa"):
        sync_production_cost(farm=other_farm, production=production, user=other_user)


@pytest.mark.django_db
def test_cost_list_separates_source_payment_and_links_production(cost_context):
    client, _user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Pasza testowa")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date.today(),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )
    CostModel.objects.create(
        farm=farm,
        production=production,
        date=date.today(),
        amount=Decimal("123.45"),
        description="Koszt paszy",
        is_paid=True,
    )

    response = client.get(reverse("cost_list"), {"year": date.today().year})
    content = response.content.decode()

    assert response.status_code == 200
    assert ">Źródło<" in content
    assert ">Płatność<" in content
    assert "Produkcja paszy" in content
    assert "Nie dotyczy" in content
    assert "Automatyczny FIFO" not in content
    assert f'href="{reverse("production_detail", args=[production.pk])}"' in content
    assert "Zobacz śrutowanie" in content
