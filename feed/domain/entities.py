from dataclasses import dataclass
from decimal import Decimal


@dataclass
class InventoryItem:
    ingredient_id: int
    ingredient_name: str
    total_delivered: Decimal
    total_used: Decimal

    @property
    def current_stock(self) -> Decimal:
        return self.total_delivered - self.total_used


@dataclass
class RecipeCostInfo:
    recipe_name: str
    cost_per_kg: Decimal

    @property
    def cost_per_ton(self) -> Decimal:
        return self.cost_per_kg * Decimal('1000')