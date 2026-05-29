import pytest
from decimal import Decimal
from datetime import date
from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel, \
    IngredientPriceConfigModel
from feed.infrastructure.repositories import FeedRepository


@pytest.mark.django_db
def test_repository_calculates_inventory_state_correctly():
    # Arrange
    ing = IngredientModel.objects.create(name="Kukurydza")
    DeliveryModel.objects.create(ingredient=ing, quantity_kg=Decimal('2000.00'), price_per_kg=Decimal('1.0'))
    DeliveryModel.objects.create(ingredient=ing, quantity_kg=Decimal('1000.00'), price_per_kg=Decimal('1.1'))

    # Tworzymy recepturę gdzie kukurydza to 50%
    recipe = RecipeModel.objects.create(name="Receptura Testowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('50.00'))

    # Produkujemy 2000 kg paszy (czyli zużywamy 1000 kg kukurydzy)
    ProductionModel.objects.create(recipe=recipe, quantity_kg=Decimal('2000.00'), date=date.today())

    repo = FeedRepository()

    # Act
    inventory = repo.get_inventory_state()

    # Assert
    assert len(inventory) == 1
    item = inventory[0]
    assert item.ingredient_name == "Kukurydza"
    assert item.total_delivered == Decimal('3000.00')
    assert item.total_used == Decimal('1000.00')
    assert item.current_stock == Decimal('2000.00')


@pytest.mark.django_db
def test_repository_calculates_recipe_costs_correctly():
    # Arrange
    ing1 = IngredientModel.objects.create(name="Pszenica")
    ing2 = IngredientModel.objects.create(name="Soja")

    IngredientPriceConfigModel.objects.create(ingredient=ing1, price_per_kg=Decimal('1.0000'))
    IngredientPriceConfigModel.objects.create(ingredient=ing2, price_per_kg=Decimal('2.0000'))

    recipe = RecipeModel.objects.create(name="Receptura B")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing1, percentage=Decimal('80.00'))  # 80% z 1.0 = 0.8
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing2, percentage=Decimal('20.00'))  # 20% z 2.0 = 0.4

    repo = FeedRepository()

    # Act
    costs = repo.get_recipe_costs()

    # Assert
    assert len(costs) == 1
    assert costs[0].recipe_name == "Receptura B"
    assert costs[0].cost_per_kg == Decimal('1.2000')  # 0.8 + 0.4