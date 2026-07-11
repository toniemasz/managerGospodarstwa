import pytest
from decimal import Decimal
from datetime import date

from django.utils import timezone

from feed.forms import DeliveryForm, IngredientForm, PriceConfigForm, ProductionForm, RecipeForm, RecipeItemFormSet
from feed.models import RecipeModel, RecipeItemModel, IngredientModel, DeliveryModel
from farms.services.farm_service import get_or_create_legacy_farm

@pytest.mark.django_db
def test_delivery_form_valid_data():
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Pszenżyto")
    form_data = {
        'date': date.today(),
        'ingredient': ing.id,
        'quantity_kg': Decimal('500.50'),
        'price_per_kg': Decimal('0.90')
    }
    form = DeliveryForm(data=form_data, farm=farm)
    assert form.is_valid() is True

@pytest.mark.django_db
def test_delivery_form_invalid_missing_ingredient():
    farm = get_or_create_legacy_farm()
    form_data = {
        'date': date.today(),
        'quantity_kg': Decimal('500.50'),
    }
    form = DeliveryForm(data=form_data, farm=farm)
    assert form.is_valid() is False
    assert 'ingredient' in form.errors


@pytest.mark.django_db
def test_recipe_item_formset_validation():
    farm = get_or_create_legacy_farm()
    ing1 = IngredientModel.objects.create(farm=farm, name="Pszenica")
    recipe = RecipeModel.objects.create(farm=farm, name="Testowa 100")

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
def test_recipe_item_formset_deletes_item_and_validates_remaining_total():
    farm = get_or_create_legacy_farm()
    recipe = RecipeModel.objects.create(farm=farm, name="Edycja receptury")
    wheat = IngredientModel.objects.create(farm=farm, name="Pszenica do usunięcia")
    soy = IngredientModel.objects.create(farm=farm, name="Soja pozostająca")
    wheat_item = RecipeItemModel.objects.create(recipe=recipe, ingredient=wheat, percentage=Decimal('60.00'))
    soy_item = RecipeItemModel.objects.create(recipe=recipe, ingredient=soy, percentage=Decimal('40.00'))

    data = {
        'items-TOTAL_FORMS': '2',
        'items-INITIAL_FORMS': '2',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-id': wheat_item.id,
        'items-0-ingredient': wheat.id,
        'items-0-percentage': '60.00',
        'items-0-DELETE': 'on',
        'items-1-id': soy_item.id,
        'items-1-ingredient': soy.id,
        'items-1-percentage': '100.00',
    }

    formset = RecipeItemFormSet(data=data, instance=recipe)

    assert formset.is_valid() is True
    formset.save()
    assert list(recipe.items.values_list('ingredient_id', 'percentage')) == [(soy.id, Decimal('100.00'))]


@pytest.mark.django_db
def test_recipe_item_formset_rejects_duplicate_ingredient():
    farm = get_or_create_legacy_farm()
    recipe = RecipeModel.objects.create(farm=farm, name="Bez duplikatów")
    ingredient = IngredientModel.objects.create(farm=farm, name="Jęczmień unikalny")
    data = {
        'items-TOTAL_FORMS': '2',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-ingredient': ingredient.id,
        'items-0-percentage': '50.00',
        'items-1-ingredient': ingredient.id,
        'items-1-percentage': '50.00',
    }

    formset = RecipeItemFormSet(data=data, instance=recipe)

    assert formset.is_valid() is False
    assert "więcej niż raz" in formset.non_form_errors()[0]


@pytest.mark.django_db
def test_production_form_custom_recipe_validation():
    farm = get_or_create_legacy_farm()
    recipe = RecipeModel.objects.create(farm=farm, name="Receptura Testowa")
    ing1 = IngredientModel.objects.create(farm=farm, name="Jęczmień")
    ing2 = IngredientModel.objects.create(farm=farm, name="Soja")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing1, percentage=Decimal('60.00'))
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing2, percentage=Decimal('40.00'))

    data = {
        'recipe': recipe.id,
        'date': timezone.now().date(),
        'quantity_kg': Decimal('150.00'),
        f'custom_percentage_{ing1.id}': '50.00',
        f'custom_percentage_{ing2.id}': '40.00',
    }
    form = ProductionForm(data=data, farm=farm)
    assert form.is_valid() is False
    assert "Proporcje składników muszą sumować się do 100%" in str(form.errors)

    data[f'custom_percentage_{ing1.id}'] = '55.00'
    data[f'custom_percentage_{ing2.id}'] = '45.00'
    form = ProductionForm(data=data, farm=farm)
    assert form.is_valid() is True
    production = form.save()
    assert production.custom_recipe_data == {str(ing1.id): '55.00', str(ing2.id): '45.00'}


@pytest.mark.django_db
def test_basic_feed_forms_are_valid():
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Premiks")

    ingredient_form = IngredientForm(data={'name': 'Serwatka', 'description': 'Płynna', 'is_in_bin': ''}, farm=farm)
    recipe_form = RecipeForm(data={'name': 'Starter'}, farm=farm)
    price_form = PriceConfigForm(data={'ingredient': ing.id, 'price_per_kg': Decimal('4.25000')}, farm=farm)

    assert ingredient_form.is_valid() is True
    assert recipe_form.is_valid() is True
    assert price_form.is_valid() is True


@pytest.mark.django_db
def test_production_form_rejects_invalid_percentage_value():
    farm = get_or_create_legacy_farm()
    recipe = RecipeModel.objects.create(farm=farm, name="JSON Test")
    ing = IngredientModel.objects.create(farm=farm, name="Pszenica")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    form = ProductionForm(data={
        'recipe': recipe.id,
        'date': timezone.now().date(),
        'quantity_kg': Decimal('150.00'),
        f'custom_percentage_{ing.id}': 'nie-liczba',
    }, farm=farm)

    assert form.is_valid() is False
    assert f'custom_percentage_{ing.id}' in form.errors
