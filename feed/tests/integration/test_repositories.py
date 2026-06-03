import pytest
from decimal import Decimal
from datetime import date

from django.utils import timezone

from feed.application.services import FeedManagementService
from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel, \
    IngredientPriceConfigModel
from feed.infrastructure.repositories import FeedRepository


@pytest.mark.django_db
def test_repository_calculates_inventory_state_correctly():
    # Arrange
    ing = IngredientModel.objects.create(name="Kukurydza")
    # DODANO DATĘ DO DOSTAWY
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
    service = FeedManagementService()
    dashboard = service.get_inventory_dashboard()['inventory']

    # Assert
    kukurydza_stock = next(i for i in dashboard if i.ingredient_id == ing.id).current_stock
    assert kukurydza_stock == Decimal('1500.00')  # 2000 dostarczono - 500 zużyto


@pytest.mark.django_db
def test_repository_fetches_raw_data_for_calculator():
    # Arrange
    ing = IngredientModel.objects.create(name="Soja")
    recipe = RecipeModel.objects.create(name="Testowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    IngredientPriceConfigModel.objects.create(ingredient=ing, price_per_kg=Decimal('2.50'))

    repo = FeedRepository()

    # Act 1: Sprawdzamy czy poprawnie pobiera mapę cen
    prices = repo.get_ingredient_prices_map()

    # Assert 1
    assert prices[ing.id] == Decimal('2.50')

    # Act 2: Sprawdzamy czy poprawnie pobiera receptury z relacjami
    recipes = repo.get_recipes_with_items()

    # Assert 2
    assert len(recipes) == 1
    assert recipes[0].items.first().ingredient == ing