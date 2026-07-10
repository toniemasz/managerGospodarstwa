import pytest
from decimal import Decimal
from django.utils import timezone

from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel
from farms.models import FarmModel
from django.contrib.auth.models import User
from feed.selectors.inventory import ingredients_for_farm, inventory_dashboard, latest_delivery_prices_map
from feed.selectors.productions import production_for_processing
from feed.selectors.recipes import recipes_with_items


@pytest.mark.django_db
def test_inventory_selector_calculates_inventory_state_correctly():
    # Arrange
    ing = IngredientModel.objects.create(name="Kukurydza")
    DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal('2000.00'),
        price_per_kg=Decimal('1.0')
    )

    recipe = RecipeModel.objects.create(name="Testowa 100")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))

    # Symulujemy zużycie
    ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('500.00'),
        status=ProductionModel.Statuses.COMPLETED
    )

    # Act
    dashboard = inventory_dashboard()['inventory']

    # Assert
    kukurydza_stock = next(i for i in dashboard if i.ingredient_id == ing.id).current_stock
    assert kukurydza_stock == Decimal('1500.00')  # 2000 dostarczono - 500 zużyto


@pytest.mark.django_db
def test_selectors_fetch_raw_data_for_calculator():
    # Arrange
    ing = IngredientModel.objects.create(name="Soja")
    DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("2.50"),
    )
    recipe = RecipeModel.objects.create(name="Testowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))

    prices = latest_delivery_prices_map()

    assert prices[ing.id] == Decimal('2.50')

    recipes = recipes_with_items()

    assert len(recipes) == 1
    assert recipes[0].items.first().ingredient == ing


@pytest.mark.django_db
def test_production_selectors_fetch_processing_data():
    ing = IngredientModel.objects.create(name="Pszenica")
    DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal('500.00'),
        price_per_kg=Decimal('1.00000'),
    )
    recipe = RecipeModel.objects.create(name="Pełnoporcjowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    queued = ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('100.00'),
        status=ProductionModel.Statuses.QUEUED,
    )
    completed = ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('200.00'),
        status=ProductionModel.Statuses.COMPLETED,
    )
    assert list(ingredients_for_farm()) == [ing]

    fetched = production_for_processing(None, queued.id)
    assert fetched.id == queued.id

    fetched.status = ProductionModel.Statuses.STAGE_1_DONE
    fetched.save()
    queued.refresh_from_db()
    assert queued.status == ProductionModel.Statuses.STAGE_1_DONE
    assert ProductionModel.objects.filter(status=ProductionModel.Statuses.COMPLETED).get() == completed


@pytest.mark.django_db
def test_inventory_selector_filters_data_by_farm():
    owner = User.objects.create_user(username='feed-owner')
    other = User.objects.create_user(username='feed-other')
    farm = FarmModel.objects.create(owner=owner, name='Gospodarstwo testowe')
    other_farm = FarmModel.objects.create(owner=other, name='Inne gospodarstwo')

    own_ingredient = IngredientModel.objects.create(name='Własny składnik', farm=farm)
    IngredientModel.objects.create(name='Cudzy składnik', farm=other_farm)

    assert list(ingredients_for_farm(farm)) == [own_ingredient]
