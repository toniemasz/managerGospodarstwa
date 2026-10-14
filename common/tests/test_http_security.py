from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from costs.models import CostCategoryModel, CostModel
from farms.services.farm_service import get_or_create_user_farm
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeModel
from sales.models import PigSaleModel
from sows.models import MortalityReportModel, SowEventModel, SowModel, VaccinationPlanModel


@pytest.mark.django_db
def test_destructive_endpoints_reject_get_and_preserve_records(client):
    user = User.objects.create_user(username="method-matrix", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Jęczmień")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("100"),
        price_per_kg=Decimal("1"),
    )
    recipe = RecipeModel.objects.create(farm=farm, name="Testowa")
    production = ProductionModel.objects.create(recipe=recipe, date=date(2026, 1, 2), quantity_kg=Decimal("50"))
    sale = PigSaleModel.objects.create(farm=farm, sale_date=date(2026, 1, 3))
    category = CostCategoryModel.objects.create(farm=farm, name="Energia")
    cost = CostModel.objects.create(farm=farm, category=category, date=date(2026, 1, 4), amount=10, description="Prąd")
    sow = SowModel.objects.create(farm=farm, ear_tag="GET-BLOCKED")
    event = SowEventModel.objects.create(sow=sow, event_type="INSEMINATION", event_date=date(2026, 1, 5))
    mortality = MortalityReportModel.objects.create(
        farm=farm,
        mortality_type=MortalityReportModel.TYPE_FINISHER,
        mortality_date=date(2026, 1, 6),
        quantity=1,
    )
    plan = VaccinationPlanModel.objects.create(farm=farm, name="Plan GET")

    urls = [
        reverse("delete_ingredient", args=[ingredient.pk]),
        reverse("delete_delivery", args=[delivery.pk]),
        reverse("delete_recipe", args=[recipe.pk]),
        reverse("delete_production", args=[production.pk]),
        reverse("delete_sale", args=[sale.pk]),
        reverse("delete_cost", args=[cost.pk]),
        reverse("deactivate_cost_category", args=[category.pk]),
        reverse("delete_sow", args=[sow.pk]),
        reverse("delete_event", args=[event.pk]),
        reverse("delete_mortality", args=[mortality.pk]),
        reverse("delete_vaccination_plan", args=[plan.pk]),
    ]

    assert [client.get(url).status_code for url in urls] == [405] * len(urls)
    assert IngredientModel.objects.filter(pk=ingredient.pk).exists()
    assert PigSaleModel.objects.filter(pk=sale.pk).exists()
    assert CostModel.objects.filter(pk=cost.pk).exists()
    assert SowModel.objects.filter(pk=sow.pk).exists()


@pytest.mark.django_db
def test_destructive_post_requires_csrf_token():
    user = User.objects.create_user(username="csrf-user", password="password")
    farm = get_or_create_user_farm(user)
    cost = CostModel.objects.create(
        farm=farm,
        date=date(2026, 1, 1),
        amount=Decimal("10.00"),
        description="Chroniony koszt",
    )
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(user)

    response = csrf_client.post(reverse("delete_cost", args=[cost.pk]))

    assert response.status_code == 403
    assert CostModel.objects.filter(pk=cost.pk).exists()
