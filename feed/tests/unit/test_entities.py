from decimal import Decimal
from feed.domain.entities import InventoryItem, RecipeCostInfo


def test_inventory_item_calculates_current_stock_correctly():
    # Arrange
    item = InventoryItem(
        ingredient_id=1,
        ingredient_name="Pszenica",
        total_delivered=Decimal('1500.00'),
        total_used=Decimal('400.00')
    )

    # Act
    stock = item.current_stock

    # Assert
    assert stock == Decimal('1100.00')


def test_recipe_cost_info_calculates_cost_per_ton_correctly():
    # Arrange
    cost_info = RecipeCostInfo(
        recipe_name="Tucznik Premium",
        cost_per_kg=Decimal('1.25')
    )

    # Act
    cost_per_ton = cost_info.cost_per_ton

    # Assert
    assert cost_per_ton == Decimal('1250.00')