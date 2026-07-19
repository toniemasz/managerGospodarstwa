import pytest
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)
from common.units import format_mass
from farms.services.farm_service import get_or_create_legacy_farm


@pytest.mark.django_db
def test_ingredient_str_representation():
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Otręby")
    # Zmieniliśmy model tak, że domyślnie is_in_bin=False daje dopisek [WOREK]
    assert str(ing) == "Otręby [WOREK]"


@pytest.mark.django_db
def test_recipe_item_percentage_validation():
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Owies")
    recipe = RecipeModel.objects.create(farm=farm, name="Testowa")

    # Tworzymy element z niedozwolonym procentem (powyżej 100%)
    item = RecipeItemModel(recipe=recipe, ingredient=ing, percentage=Decimal('150.00'))

    # W Django walidatory modelu uruchamiają się przez full_clean(), a nie samo save()
    with pytest.raises(ValidationError):
        item.full_clean()


@pytest.mark.django_db
def test_recipe_cannot_contain_the_same_ingredient_twice_at_database_level():
    farm = get_or_create_legacy_farm()
    ingredient = IngredientModel.objects.create(farm=farm, name='Unikalny składnik')
    recipe = RecipeModel.objects.create(farm=farm, name='Unikalna receptura')
    RecipeItemModel.objects.create(
        recipe=recipe,
        ingredient=ingredient,
        percentage=Decimal('50.00'),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        RecipeItemModel.objects.create(
            recipe=recipe,
            ingredient=ingredient,
            percentage=Decimal('50.00'),
        )


@pytest.mark.django_db
def test_feed_model_string_representations_and_status_label():
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Jęczmień", is_in_bin=True)
    delivery = DeliveryModel.objects.create(
        ingredient=ing,
        date=date(2026, 6, 1),
        quantity_kg=Decimal('1250.50'),
        price_per_kg=Decimal('0.80000'),
    )
    price = IngredientPriceConfigModel.objects.create(ingredient=ing, price_per_kg=Decimal('0.85000'))
    recipe = RecipeModel.objects.create(farm=farm, name="Grower")
    item = RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    production = ProductionModel.objects.create(
        date=date(2026, 6, 2),
        recipe=recipe,
        quantity_kg=Decimal('500.00'),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )

    assert str(ing) == "Jęczmień [BIN]"
    assert str(delivery) == f"Dostawa: Jęczmień - {format_mass(Decimal('1250.50'))} (2026-06-01)"
    assert str(price) == "Cena: Jęczmień - 0.85000 PLN/kg"
    assert str(recipe) == "Grower"
    assert str(item) == "Grower - Jęczmień (100.00%)"
    assert production.status_label == "Etap 1 zakończony (Biny)"
    assert str(production) == f"Śrutowanie: Grower ({format_mass(Decimal('500.00'))}) - Etap 1 zakończony (Biny)"
