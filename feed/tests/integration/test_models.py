import pytest
from django.core.exceptions import ValidationError
from decimal import Decimal
from feed.models import IngredientModel, RecipeModel, RecipeItemModel


@pytest.mark.django_db
def test_ingredient_str_representation():
    ing = IngredientModel.objects.create(name="Otręby")
    assert str(ing) == "Otręby"


@pytest.mark.django_db
def test_recipe_item_percentage_validation():
    ing = IngredientModel.objects.create(name="Owies")
    recipe = RecipeModel.objects.create(name="Testowa")

    # Tworzymy element z niedozwolonym procentem (powyżej 100%)
    item = RecipeItemModel(recipe=recipe, ingredient=ing, percentage=Decimal('150.00'))

    # Assert
    with pytest.raises(ValidationError):
        item.full_clean()  # Wymusza uruchomienie walidatorów modelu

    # Zbyt mały procent
    item2 = RecipeItemModel(recipe=recipe, ingredient=ing, percentage=Decimal('-5.00'))
    with pytest.raises(ValidationError):
        item2.full_clean()