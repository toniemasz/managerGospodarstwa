from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from farms.services.farm_service import get_or_create_user_farm
from feed.models import DeliveryModel, IngredientModel, ProductionIngredientUsageModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.selectors.production_costs import ProductionCostSelector
from feed.actions.productions import complete_production
from feed.actions.inventory import InventoryActions


@pytest.mark.django_db
def test_actual_feed_cost_uses_fifo_delivery_batches():
    user = get_user_model().objects.create_user(username="feed-cost")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Zboże")
    first_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.20000"),
    )
    second_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 6, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.50000"),
    )
    InventoryActions(farm).sync_delivery(first_delivery)
    InventoryActions(farm).sync_delivery(second_delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="FIFO")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    first_production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("800.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    second_production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 7, 1),
        quantity_kg=Decimal("400.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    assert complete_production(farm, first_production.pk, user=user, create_serving=False)[0]
    assert complete_production(farm, second_production.pk, user=user, create_serving=False)[0]
    ProductionModel.objects.create(recipe=recipe, date=date(2026, 7, 2), quantity_kg=9000, status=ProductionModel.Statuses.QUEUED)

    result = ProductionCostSelector(farm).calculate(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
    assert result["quantity_kg"] == Decimal("1200.00")
    assert result["total_cost"] == Decimal("1500.00")
    assert result["average_cost_per_kg"] == Decimal("1.25")
    assert result["recipe_ranking"][0]["recipe_name"] == "FIFO"
    assert ProductionIngredientUsageModel.objects.filter(delivery=first_delivery).count() == 2
    assert ProductionIngredientUsageModel.objects.filter(delivery=second_delivery).count() == 1
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_delivery.remaining_quantity_kg == Decimal("0.00")
    assert second_delivery.remaining_quantity_kg == Decimal("800.00")


@pytest.mark.django_db
def test_legacy_feed_cost_marks_missing_price_as_partial_instead_of_zero():
    user = get_user_model().objects.create_user(username="feed-cost-missing")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Soja")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=None,
    )
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="Legacy")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    production = ProductionModel(
        recipe=recipe,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("800.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )
    production._skip_inventory_sync = True
    production.save()

    result = ProductionCostSelector(farm).calculate()
    detail = result["details"][0]

    assert detail["production"] == production
    assert detail["is_partial"] is True
    assert result["total_cost"] == Decimal("0.00")
    assert "Brak zapisanego kosztu produkcji paszy" in detail["cost_note"]
    assert detail["components"] == []
