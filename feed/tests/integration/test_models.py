import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from feed.models import IngredientModel, RecipeModel, RecipeItemModel


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