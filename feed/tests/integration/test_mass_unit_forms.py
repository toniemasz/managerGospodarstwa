from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from farms.services.farm_service import get_or_create_user_farm
from feed.forms import (
    DeliveryForm,
    FeedServingForm,
    IngredientForm,
    InventoryAdjustmentForm,
    ProductionForm,
    ReadyFeedPurchaseForm,
)
from feed.models import FeedProductModel, IngredientModel, RecipeItemModel, RecipeModel


@pytest.mark.django_db
def test_all_feed_mass_forms_convert_tonnes_to_stored_kilograms():
    user = User.objects.create_user(username="mass-feed-forms")
    farm = get_or_create_user_farm(user)

    ingredient_form = IngredientForm(data={
        "name": "Pszenica jednostki",
        "description": "",
        "low_stock_threshold_kg": "1.5",
        "low_stock_threshold_kg_unit": "t",
        "is_in_bin": "on",
    }, farm=farm)
    assert ingredient_form.is_valid(), ingredient_form.errors
    ingredient = ingredient_form.save()
    assert ingredient.low_stock_threshold_kg == Decimal("1500.00")

    delivery_form = DeliveryForm(data={
        "date": date.today().isoformat(),
        "ingredient": ingredient.pk,
        "quantity_kg": "2.25",
        "quantity_kg_unit": "t",
        "price_per_kg": "1.00000",
    }, farm=farm)
    assert delivery_form.is_valid(), delivery_form.errors
    delivery = delivery_form.save()
    assert delivery.quantity_kg == Decimal("2250.00")

    recipe = RecipeModel.objects.create(farm=farm, name="Receptura jednostki")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal("100.00"))
    production_form = ProductionForm(data={
        "date": date.today().isoformat(),
        "time": "08:00",
        "recipe": recipe.pk,
        "quantity_kg": "3.125",
        "quantity_kg_unit": "t",
    }, farm=farm)
    assert production_form.is_valid(), production_form.errors
    production = production_form.save()
    assert production.quantity_kg == Decimal("3125.00")

    adjustment_form = InventoryAdjustmentForm(data={
        "ingredient": ingredient.pk,
        "movement_date": date.today().isoformat(),
        "quantity_kg": "0.25",
        "quantity_kg_unit": "t",
        "direction": "plus",
        "reason": "Test jednostek",
    }, farm=farm)
    assert adjustment_form.is_valid(), adjustment_form.errors
    assert adjustment_form.cleaned_data["quantity_kg"] == Decimal("250.00")

    purchase_form = ReadyFeedPurchaseForm(data={
        "product_name": "Gotowa jednostki",
        "date": date.today().isoformat(),
        "quantity_kg": "1.75",
        "quantity_kg_unit": "t",
        "price_per_kg": "2.00000",
    }, farm=farm)
    assert purchase_form.is_valid(), purchase_form.errors
    assert purchase_form.cleaned_data["quantity_kg"] == Decimal("1750.00")

    product = FeedProductModel.objects.create(
        farm=farm,
        name="Podanie jednostki",
        source_type=FeedProductModel.SourceTypes.PURCHASED_READY,
    )
    serving_form = FeedServingForm(data={
        "product": product.pk,
        "date": date.today().isoformat(),
        "time": "09:00",
        "quantity_kg": "1.2",
        "quantity_kg_unit": "t",
        "note": "Test",
    }, farm=farm)
    assert serving_form.is_valid(), serving_form.errors
    assert serving_form.cleaned_data["quantity_kg"] == Decimal("1200.00")


@pytest.mark.django_db
def test_editing_feed_mass_defaults_to_tonnes_but_saves_back_in_kilograms():
    user = User.objects.create_user(username="mass-edit-form")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(
        farm=farm,
        name="Jęczmień jednostki",
        low_stock_threshold_kg=Decimal("2500.00"),
    )

    form = IngredientForm(instance=ingredient, farm=farm)

    assert form["low_stock_threshold_kg"].value() == "2.5"
    assert form["low_stock_threshold_kg_unit"].value() == "t"
