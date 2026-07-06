from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from farms.services.farm_service import get_or_create_user_farm
from feed.actions.deliveries import create_delivery, delete_delivery, update_delivery
from feed.actions.recipes import create_recipe, update_recipe
from feed.forms import DeliveryForm, RecipeForm, RecipeItemFormSet
from feed.models import (
    DeliveryModel,
    IngredientModel,
    InventoryMovementModel,
    RecipeItemModel,
    RecipeModel,
    RecipeVersionModel,
)


@pytest.fixture
def farm_user():
    user = get_user_model().objects.create_user(username="feed-action-user")
    return user, get_or_create_user_farm(user)


@pytest.mark.django_db
def test_delivery_actions_sync_inventory_movements(farm_user):
    user, farm = farm_user
    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica")
    form = DeliveryForm(data={
        "date": date(2026, 7, 1),
        "ingredient": ingredient.id,
        "quantity_kg": "100.00",
        "price_per_kg": "1.20000",
    }, farm=farm)

    assert form.is_valid() is True
    delivery = create_delivery(form, farm=farm, user=user)

    movement = InventoryMovementModel.objects.get(
        farm=farm,
        ingredient=ingredient,
        movement_type=InventoryMovementModel.Types.DELIVERY,
    )
    assert movement.quantity_kg == Decimal("100.00")

    update_form = DeliveryForm(data={
        "date": date(2026, 7, 2),
        "ingredient": ingredient.id,
        "quantity_kg": "150.00",
        "price_per_kg": "1.30000",
    }, instance=delivery, farm=farm)

    assert update_form.is_valid() is True
    delivery = update_delivery(update_form, farm=farm, user=user)
    movement = InventoryMovementModel.objects.get(
        farm=farm,
        ingredient=ingredient,
        movement_type=InventoryMovementModel.Types.DELIVERY,
    )
    delivery.refresh_from_db()
    assert delivery.quantity_kg == Decimal("150.00")
    assert movement.quantity_kg == Decimal("150.00")

    delete_delivery(delivery, farm=farm)

    assert not DeliveryModel.objects.filter(pk=delivery.pk).exists()
    assert not InventoryMovementModel.objects.filter(pk=movement.pk).exists()


@pytest.mark.django_db
def test_recipe_actions_create_and_update_recipe_versions(farm_user):
    user, farm = farm_user
    wheat = IngredientModel.objects.create(farm=farm, name="Pszenica")
    soy = IngredientModel.objects.create(farm=farm, name="Soja")
    recipe = RecipeModel(farm=farm)
    form = RecipeForm(data={"name": "Grower"}, instance=recipe, farm=farm)
    formset = RecipeItemFormSet(data={
        "items-TOTAL_FORMS": "1",
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "items-0-ingredient": wheat.id,
        "items-0-percentage": "100.00",
    }, instance=recipe, form_kwargs={"farm": farm})

    assert form.is_valid() is True
    assert formset.is_valid() is True
    recipe = create_recipe(form, formset, farm=farm, user=user)

    first_item = RecipeItemModel.objects.get(recipe=recipe)
    first_version = RecipeVersionModel.objects.get(recipe=recipe, is_current=True)
    assert first_version.version_number == 1

    edit_form = RecipeForm(data={"name": "Grower"}, instance=recipe, farm=farm)
    edit_formset = RecipeItemFormSet(data={
        "items-TOTAL_FORMS": "2",
        "items-INITIAL_FORMS": "1",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
        "items-0-id": first_item.id,
        "items-0-ingredient": wheat.id,
        "items-0-percentage": "50.00",
        "items-1-ingredient": soy.id,
        "items-1-percentage": "50.00",
    }, instance=recipe, form_kwargs={"farm": farm})

    assert edit_form.is_valid() is True
    assert edit_formset.is_valid() is True
    recipe, version_created = update_recipe(edit_form, edit_formset, farm=farm, user=user)

    assert version_created is True
    assert RecipeVersionModel.objects.filter(recipe=recipe).count() == 2
    assert RecipeVersionModel.objects.get(recipe=recipe, is_current=True).version_number == 2
