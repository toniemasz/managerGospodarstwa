from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.urls import reverse

from farms.services.farm_service import get_or_create_user_farm
from feed.models import DeliveryModel, IngredientModel, InventoryMovementModel, ProductionIngredientUsageModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.services.feed_management_service import FeedManagementService
from feed.services.inventory_service import InventoryMovementService
from feed.forms import InventoryAdjustmentForm


@pytest.fixture
def inventory_data():
    user = User.objects.create_user(username="inventory")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Jęczmień")
    DeliveryModel.objects.create(ingredient=ingredient, date=date.today(), quantity_kg=1000, price_per_kg=1)
    recipe = RecipeModel.objects.create(farm=farm, name="100% jęczmień")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    return user, farm, ingredient, recipe


@pytest.mark.django_db
def test_delivery_production_and_repeated_completion_movements(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    assert InventoryMovementService(farm).balances()[ingredient.pk] == Decimal("1000")
    production = ProductionModel.objects.create(recipe=recipe, date=date.today(), quantity_kg=400, status=ProductionModel.Statuses.STAGE_1_DONE)
    service = FeedManagementService(farm)
    assert service.complete_production(production.pk, user=user)[0] is True
    assert service.complete_production(production.pk, user=user)[0] is False
    assert InventoryMovementModel.objects.filter(farm=farm, movement_type="PRODUCTION_USAGE").count() == 1
    assert InventoryMovementService(farm).balances()[ingredient.pk] == Decimal("600")


@pytest.mark.django_db
def test_completed_production_edit_and_delete_rebuilds_fifo_usage(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    DeliveryModel.objects.all().delete()
    first_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.20000"),
    )
    second_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.50000"),
    )
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 3, 1),
        quantity_kg=Decimal("1200.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    assert FeedManagementService(farm).complete_production(production.pk, user=user)[0] is True
    production.refresh_from_db()
    assert production.feed_cost_total == Decimal("1500.00")
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 2
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_delivery.remaining_quantity_kg == Decimal("0.00")
    assert second_delivery.remaining_quantity_kg == Decimal("800.00")

    production.quantity_kg = Decimal("500.00")
    production.save()
    production.refresh_from_db()
    assert production.feed_cost_total == Decimal("600.00")
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 1
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_delivery.remaining_quantity_kg == Decimal("500.00")
    assert second_delivery.remaining_quantity_kg == Decimal("1000.00")

    production.delete()
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_delivery.remaining_quantity_kg == Decimal("1000.00")
    assert second_delivery.remaining_quantity_kg == Decimal("1000.00")
    assert not ProductionIngredientUsageModel.objects.exists()
    assert not InventoryMovementModel.objects.filter(movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE).exists()


@pytest.mark.django_db
def test_positive_negative_adjustments_and_cross_farm_isolation(inventory_data):
    user, farm, ingredient, _ = inventory_data
    service = InventoryMovementService(farm)
    service.adjust(ingredient=ingredient, quantity_kg=100, direction="plus", movement_date=date.today(), reason="remanent", user=user)
    service.adjust(ingredient=ingredient, quantity_kg=50, direction="minus", movement_date=date.today(), reason="ubytek", user=user)
    assert service.balances()[ingredient.pk] == Decimal("1050")
    with pytest.raises(ValidationError):
        service.adjust(ingredient=ingredient, quantity_kg=2000, direction="minus", movement_date=date.today(), reason="błąd", user=user)

    other_user = User.objects.create_user(username="other-inventory")
    other_farm = get_or_create_user_farm(other_user)
    assert not InventoryMovementModel.objects.filter(farm=other_farm).exists()


@pytest.mark.django_db
def test_inventory_adjustment_form_and_view(client, inventory_data):
    user, farm, ingredient, _ = inventory_data
    invalid = InventoryAdjustmentForm({
        "ingredient": ingredient.pk,
        "movement_date": "not-a-date",
        "quantity_kg": "not-a-decimal",
        "direction": "minus",
        "reason": "test",
    }, farm=farm)
    assert not invalid.is_valid()

    client.force_login(user)
    response = client.post(reverse("inventory_adjustment"), {
        "ingredient": ingredient.pk,
        "movement_date": date.today().isoformat(),
        "quantity_kg": "25.50",
        "direction": "plus",
        "reason": "remanent",
    })
    assert response.status_code == 302
    assert InventoryMovementModel.objects.filter(
        farm=farm,
        movement_type=InventoryMovementModel.Types.ADJUSTMENT_POSITIVE,
        quantity_kg=Decimal("25.50"),
    ).exists()
