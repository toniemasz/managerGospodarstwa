import pytest
from decimal import Decimal
from datetime import date

from django.utils import timezone

from feed.forms import DeliveryForm, IngredientForm, PriceConfigForm, ProductionForm, RecipeForm, RecipeItemFormSet
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
    ing1 = IngredientModel.objects.create(name="Jęczmień")
    ing2 = IngredientModel.objects.create(name="Soja")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing1, percentage=Decimal('60.00'))
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing2, percentage=Decimal('40.00'))

    data = {
        'recipe': recipe.id,
        'date': timezone.now().date(),
        'quantity_kg': Decimal('150.00'),
        f'custom_percentage_{ing1.id}': '50.00',
        f'custom_percentage_{ing2.id}': '40.00',
    }
    form = ProductionForm(data=data)
    assert form.is_valid() is False
    assert "Proporcje składników muszą sumować się do 100%" in str(form.errors)

    data[f'custom_percentage_{ing1.id}'] = '55.00'
    data[f'custom_percentage_{ing2.id}'] = '45.00'
    form = ProductionForm(data=data)
    assert form.is_valid() is True
    production = form.save()
    assert production.custom_recipe_data == {str(ing1.id): '55.00', str(ing2.id): '45.00'}


@pytest.mark.django_db
def test_basic_feed_forms_are_valid():
    ing = IngredientModel.objects.create(name="Premiks")

    ingredient_form = IngredientForm(data={'name': 'Serwatka', 'description': 'Płynna', 'is_in_bin': ''})
    recipe_form = RecipeForm(data={'name': 'Starter'})
    price_form = PriceConfigForm(data={'ingredient': ing.id, 'price_per_kg': Decimal('4.25000')})

    assert ingredient_form.is_valid() is True
    assert recipe_form.is_valid() is True
    assert price_form.is_valid() is True


@pytest.mark.django_db
def test_production_form_rejects_invalid_percentage_value():
    recipe = RecipeModel.objects.create(name="JSON Test")
    ing = IngredientModel.objects.create(name="Pszenica")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    form = ProductionForm(data={
        'recipe': recipe.id,
        'date': timezone.now().date(),
        'quantity_kg': Decimal('150.00'),
        f'custom_percentage_{ing.id}': 'nie-liczba',
    })

    assert form.is_valid() is False
    assert f'custom_percentage_{ing.id}' in form.errors
