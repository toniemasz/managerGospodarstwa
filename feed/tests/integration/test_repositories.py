import pytest
from decimal import Decimal
from django.utils import timezone

from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel
from farms.models import FarmModel
from django.contrib.auth.models import User
from feed.selectors.inventory import ingredients_for_farm, inventory_dashboard, latest_delivery_prices_map
from feed.selectors.productions import production_for_processing
from feed.selectors.recipes import recipes_with_items
from feed.actions.productions import complete_production
from feed.actions.inventory import InventoryActions
from farms.services.farm_service import get_or_create_legacy_farm


@pytest.mark.django_db
def test_inventory_selector_calculates_inventory_state_correctly():
    # Arrange
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Kukurydza")
    delivery = DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal('2000.00'),
        price_per_kg=Decimal('1.0')
    )
    InventoryActions(farm).sync_delivery(delivery)

    recipe = RecipeModel.objects.create(farm=farm, name="Testowa 100")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))

    # Symulujemy zużycie
    production = ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('500.00'),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    assert complete_production(ing.farm, production.pk, user=ing.farm.owner)[0]

    # Act
    dashboard = inventory_dashboard(farm)['inventory']

    # Assert
    kukurydza_stock = next(i for i in dashboard if i.ingredient_id == ing.id).current_stock
    assert kukurydza_stock == Decimal('1500.00')  # 2000 dostarczono - 500 zużyto


@pytest.mark.django_db
def test_selectors_fetch_raw_data_for_calculator():
    # Arrange
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Soja")
    DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("2.50"),
    )
    recipe = RecipeModel.objects.create(farm=farm, name="Testowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))

    prices = latest_delivery_prices_map(farm)

    assert prices[ing.id] == Decimal('2.50')

    recipes = recipes_with_items(farm)

    assert len(recipes) == 1
    assert recipes[0].items.first().ingredient == ing


@pytest.mark.django_db
def test_production_selectors_fetch_processing_data():
    farm = get_or_create_legacy_farm()
    ing = IngredientModel.objects.create(farm=farm, name="Pszenica")
    DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal('500.00'),
        price_per_kg=Decimal('1.00000'),
    )
    recipe = RecipeModel.objects.create(farm=farm, name="Pełnoporcjowa")
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
    assert list(ingredients_for_farm(farm)) == [ing]

    fetched = production_for_processing(recipe.farm, queued.id)
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
