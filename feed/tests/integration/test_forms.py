import pytest
from decimal import Decimal
from datetime import date

from django.utils import timezone

from feed.forms import DeliveryForm
from feed.forms import ProductionForm, RecipeItemFormSet
from feed.models import RecipeModel, RecipeItemModel, IngredientModel, DeliveryModel

@pytest.mark.django_db
def test_delivery_form_valid_data():
    ing = IngredientModel.objects.create(name="Pszenżyto")
    form_data = {
        'date': date.today(),
        'ingredient': ing.id,
        'quantity_kg': Decimal('500.50'),
        'price_per_kg': Decimal('0.90')
    }
    form = DeliveryForm(data=form_data)
    assert form.is_valid() is True

@pytest.mark.django_db
def test_delivery_form_invalid_missing_ingredient():
    form_data = {
        'date': date.today(),
        'quantity_kg': Decimal('500.50'),
    }
    form = DeliveryForm(data=form_data)
    assert form.is_valid() is False
    assert 'ingredient' in form.errors


@pytest.mark.django_db
def test_recipe_item_formset_validation():
    ing1 = IngredientModel.objects.create(name="Pszenica")
    recipe = RecipeModel.objects.create(name="Testowa 100")

    data = {
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-ingredient': ing1.id,
        'items-0-percentage': '99.00',
    }
    formset = RecipeItemFormSet(data=data, instance=recipe)
    assert formset.is_valid() is False
    assert "Suma procentowych udziałów składników musi wynosić równe 100%" in formset.non_form_errors()[0]

    data['items-0-percentage'] = '100.00'
    formset = RecipeItemFormSet(data=data, instance=recipe)
    assert formset.is_valid() is True


@pytest.mark.django_db
def test_production_form_custom_recipe_validation():
    recipe = RecipeModel.objects.create(name="Receptura Testowa")

    # Próba wysłania JSONa z proporcjami nie dającymi 100%
    data = {
        'recipe': recipe.id,
        'date': timezone.now().date(),
        'quantity_kg': Decimal('150.00'),
        'custom_recipe_data': '{"1": 50.0, "2": 40.0}'  # Daje 90%
    }
    form = ProductionForm(data=data)
    assert form.is_valid() is False
    assert "Zmienione proporcje muszą sumować się do 100%" in str(form.errors)

    # Poprawny JSON
    data['custom_recipe_data'] = '{"1": 60.0, "2": 40.0}'
    form = ProductionForm(data=data)
    assert form.is_valid() is True