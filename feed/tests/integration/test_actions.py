from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from farms.services.farm_service import get_or_create_user_farm
from feed.actions.deliveries import create_delivery, delete_delivery, update_delivery
from feed.actions.ingredients import create_ingredient, delete_ingredient, update_ingredient
from feed.actions.productions import create_production
from feed.actions.recipes import create_recipe, delete_recipe, update_recipe
from feed.forms import DeliveryForm, IngredientForm, ProductionForm, RecipeForm, RecipeItemFormSet
from feed.models import (
    DeliveryModel,
    IngredientModel,
    InventoryMovementModel,
    ProductionModel,
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
def test_ingredient_actions_create_update_and_delete(farm_user):
    _, farm = farm_user
    form = IngredientForm(data={
        "name": "Jęczmień",
        "description": "",
        "low_stock_threshold_kg": "300.00",
        "is_in_bin": "on",
    }, farm=farm)

    assert form.is_valid() is True
    ingredient = create_ingredient(form, farm=farm)

    assert ingredient.farm == farm
    assert ingredient.name == "Jęczmień"

    update_form = IngredientForm(data={
        "name": "Jęczmień paszowy",
        "description": "po korekcie",
        "low_stock_threshold_kg": "250.00",
        "is_in_bin": "",
    }, instance=ingredient, farm=farm)

    assert update_form.is_valid() is True
    ingredient = update_ingredient(update_form)
    assert ingredient.name == "Jęczmień paszowy"
    assert ingredient.low_stock_threshold_kg == Decimal("250.00")

    ingredient_id = ingredient.pk
    deleted_ingredient = delete_ingredient(ingredient)

    assert deleted_ingredient.model_label == "feed.IngredientModel"
    assert deleted_ingredient.object_id == ingredient_id
    assert not IngredientModel.objects.filter(pk=ingredient_id).exists()


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


@pytest.mark.django_db
def test_delete_recipe_action_removes_unused_recipe(farm_user):
    _, farm = farm_user
    recipe = RecipeModel.objects.create(farm=farm, name="Do usunięcia")
    recipe_id = recipe.pk

    deleted_recipe = delete_recipe(recipe)

    assert deleted_recipe == {
        "model_label": "feed.RecipeModel",
        "object_id": recipe_id,
        "object_repr": "Do usunięcia",
    }
    assert not RecipeModel.objects.filter(pk=recipe_id).exists()


@pytest.mark.django_db
def test_create_production_action_preserves_current_recipe_version(farm_user):
    user, farm = farm_user
    wheat = IngredientModel.objects.create(farm=farm, name="Pszenica")
    recipe = RecipeModel(farm=farm)
    form = RecipeForm(data={"name": "Starter"}, instance=recipe, farm=farm)
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
    current_version = RecipeVersionModel.objects.get(recipe=recipe, is_current=True)

    production_form = ProductionForm(data={
        "date": date(2026, 7, 3),
        "time": "08:00",
        "recipe": recipe.id,
        "quantity_kg": "250.00",
    }, farm=farm)

    assert production_form.is_valid() is True
    production = create_production(production_form)

    assert production.status == ProductionModel.Statuses.QUEUED
    assert production.recipe_version == current_version
