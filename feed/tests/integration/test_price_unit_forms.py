from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from farms.services.farm_service import get_or_create_user_farm
from feed.forms import DeliveryForm, ReadyFeedDeliveryForm
from feed.models import IngredientModel


@pytest.mark.django_db
def test_delivery_form_converts_price_per_tonne_to_stored_price_per_kg():
    user = User.objects.create_user(username="delivery-price-unit")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica cena za tonę")

    form = DeliveryForm(data={
        "date": date.today().isoformat(),
        "ingredient": ingredient.pk,
        "quantity_kg": "2",
        "quantity_kg_unit": "t",
        "price_per_kg": "1250.00",
        "price_unit": "t",
    }, farm=farm)

    assert form.is_valid(), form.errors
    delivery = form.save()

    assert delivery.quantity_kg == Decimal("2000.00")
    assert delivery.price_per_kg == Decimal("1.25000")


@pytest.mark.django_db
def test_delivery_form_keeps_price_per_kg_for_existing_posts_without_price_unit():
    user = User.objects.create_user(username="delivery-price-default-unit")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Jęczmień cena za kg")

    form = DeliveryForm(data={
        "date": date.today().isoformat(),
        "ingredient": ingredient.pk,
        "quantity_kg": "1000",
        "quantity_kg_unit": "kg",
        "price_per_kg": "1.12500",
    }, farm=farm)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["price_per_kg"] == Decimal("1.12500")


def test_ready_feed_delivery_form_converts_price_per_tonne_to_price_per_kg():
    form = ReadyFeedDeliveryForm(data={
        "date": date.today().isoformat(),
        "quantity_kg": "1.5",
        "quantity_kg_unit": "t",
        "price_per_kg": "2100.00",
        "price_unit": "t",
    })

    assert form.is_valid(), form.errors
    assert form.cleaned_data["quantity_kg"] == Decimal("1500.00")
    assert form.cleaned_data["price_per_kg"] == Decimal("2.10000")
