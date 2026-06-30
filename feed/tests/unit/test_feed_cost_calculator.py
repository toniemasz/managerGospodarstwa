from datetime import date
from decimal import Decimal

import pytest

from feed.forms import CalculatorPriceForm
from feed.models import DeliveryModel, IngredientModel, RecipeItemModel, RecipeModel
from feed.services.feed_calculators import RecipeCostCalculator
from feed.services.feed_management_service import FeedManagementService


def test_recipe_cost_calculates_percentage_of_one_tonne():
    calculator = RecipeCostCalculator(
        recipe_id=1,
        recipe_name="Starter",
        recipe_items=[
            {
                "ingredient_id": 10,
                "ingredient_name": "Premiks",
                "percentage": Decimal("7.00"),
            },
        ],
        price_map={10: Decimal("2.50000")},
    )

    cost = calculator.calculate_cost()

    assert cost.is_complete is True
    assert cost.cost_per_kg == Decimal("0.1750000")
    assert cost.cost_per_ton == Decimal("175.0000000")
    assert cost.item_costs[0]["quantity_per_ton_kg"] == Decimal("70.0000")
    assert cost.item_costs[0]["cost_per_ton"] == Decimal("175.0000000")


def test_recipe_cost_marks_missing_price_without_free_ingredient():
    calculator = RecipeCostCalculator(
        recipe_id=1,
        recipe_name="Starter",
        recipe_items=[
            {
                "ingredient_id": 10,
                "ingredient_name": "Premiks",
                "percentage": Decimal("7.00"),
            },
        ],
        price_map={},
    )

    cost = calculator.calculate_cost()

    assert cost.is_complete is False
    assert cost.missing_price_ingredients == ["Premiks"]
    assert cost.item_costs[0]["has_price"] is False
    assert cost.item_costs[0]["price_per_kg"] is None
    assert cost.item_costs[0]["cost_per_kg"] is None
    assert cost.item_costs[0]["cost_per_ton"] is None


@pytest.mark.django_db
def test_service_does_not_convert_null_delivery_price_to_zero():
    ingredient = IngredientModel.objects.create(name="Soja")
    DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date.today(),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=None,
    )
    recipe = RecipeModel.objects.create(name="Starter")
    RecipeItemModel.objects.create(
        recipe=recipe,
        ingredient=ingredient,
        percentage=Decimal("100.00"),
    )

    service = FeedManagementService()
    prices = service.repository.get_latest_delivery_prices_map()
    costs = service.get_recipe_costs()

    assert ingredient.id not in prices
    assert costs[0].is_complete is False
    assert costs[0].missing_price_ingredients == ["Soja"]
    assert costs[0].item_costs[0]["price_per_kg"] is None


@pytest.mark.django_db
def test_service_treats_zero_delivery_price_as_missing_price():
    ingredient = IngredientModel.objects.create(name="Kukurydza")
    DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date.today(),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("0.00000"),
    )
    recipe = RecipeModel.objects.create(name="Starter")
    RecipeItemModel.objects.create(
        recipe=recipe,
        ingredient=ingredient,
        percentage=Decimal("100.00"),
    )

    service = FeedManagementService()
    costs = service.get_recipe_costs()

    assert costs[0].is_complete is False
    assert costs[0].missing_price_ingredients == ["Kukurydza"]
    assert costs[0].item_costs[0]["cost_per_ton"] is None


@pytest.mark.django_db
def test_calculator_price_form_rejects_zero_price_override():
    ingredient = IngredientModel.objects.create(name="Pszenica")
    field_name = CalculatorPriceForm.field_name_for_ingredient(ingredient.id)
    form = CalculatorPriceForm(
        data={field_name: "0"},
        ingredients=[ingredient],
        prices={},
    )

    assert form.is_valid() is False
    assert "musi być większa od 0" in str(form.errors[field_name])
