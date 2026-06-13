import pytest
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError
from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)


@pytest.mark.django_db
def test_ingredient_str_representation():
    ing = IngredientModel.objects.create(name="Otręby")
    # Zmieniliśmy model tak, że domyślnie is_in_bin=False daje dopisek [WOREK]
    assert str(ing) == "Otręby [WOREK]"


@pytest.mark.django_db
def test_recipe_item_percentage_validation():
    ing = IngredientModel.objects.create(name="Owies")
    recipe = RecipeModel.objects.create(name="Testowa")

    # Tworzymy element z niedozwolonym procentem (powyżej 100%)
    item = RecipeItemModel(recipe=recipe, ingredient=ing, percentage=Decimal('150.00'))

    # W Django walidatory modelu uruchamiają się przez full_clean(), a nie samo save()
    with pytest.raises(ValidationError):
        item.full_clean()


@pytest.mark.django_db
def test_feed_model_string_representations_and_status_label():
    ing = IngredientModel.objects.create(name="Jęczmień", is_in_bin=True)
    delivery = DeliveryModel.objects.create(
        ingredient=ing,
        date=date(2026, 6, 1),
        quantity_kg=Decimal('1250.50'),
        price_per_kg=Decimal('0.80000'),
    )
    price = IngredientPriceConfigModel.objects.create(ingredient=ing, price_per_kg=Decimal('0.85000'))
    recipe = RecipeModel.objects.create(name="Grower")
    item = RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    production = ProductionModel.objects.create(
        date=date(2026, 6, 2),
        recipe=recipe,
        quantity_kg=Decimal('500.00'),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )

    assert str(ing) == "Jęczmień [BIN]"
    assert str(delivery) == "Dostawa: Jęczmień - 1250.50kg (2026-06-01)"
    assert str(price) == "Cena: Jęczmień - 0.85000 PLN/kg"
    assert str(recipe) == "Grower"
    assert str(item) == "Grower - Jęczmień (100.00%)"
    assert production.status_label == "Etap 1 zakończony (Biny)"
    assert str(production) == "Śrutowanie: Grower (500.00kg) - Etap 1 zakończony (Biny)"
