from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class InventoryItem:
    """Calculated stock state for one ingredient."""
    ingredient_id: int
    name: str
    total_delivered: Decimal
    total_used: Decimal
    is_in_bin: bool = False
    low_stock_threshold_kg: Decimal = Decimal('500.00')

    @property
    def current_stock(self) -> Decimal:
        return self.total_delivered - self.total_used

    @property
    def is_low_stock(self) -> bool:
        return self.current_stock < self.low_stock_threshold_kg

    @property
    def threshold_difference(self) -> Decimal:
        return self.current_stock - self.low_stock_threshold_kg

    def current_stock_in_t(self) -> Decimal:
        return self.current_stock/Decimal('1000.00')


@dataclass
class RecipeCostInfo:
    """Calculated cost for one feed recipe."""
    recipe_name: str
    cost_per_kg: Decimal
    recipe_id: int | None = None
    item_costs: List[Dict] | None = None
    missing_price_ingredients: List[str] | None = None

    @property
    def cost_per_ton(self) -> Decimal:
        return self.cost_per_kg * Decimal('1000.00')

    @property
    def is_complete(self) -> bool:
        return not self.missing_price_ingredients


@dataclass
class IngredientRequirement:
    """Ingredient quantity required for one production batch."""
    ingredient_id: int
    name: str
    is_in_bin: bool
    percentage: Decimal
    required_kg: Decimal


class ProductionCalculator:
    """Pure calculations for recipe percentages and ingredient quantities."""

    def __init__(self, quantity_kg: Decimal, base_recipe_items: List[Dict], custom_recipe_data: Optional[Dict] = None):
        self.quantity_kg = Decimal(str(quantity_kg))
        self.base_recipe_items = base_recipe_items

        self.custom_proportions: Dict[int, Decimal] = {}
        if custom_recipe_data:
            for k, v in custom_recipe_data.items():
                self.custom_proportions[int(k)] = Decimal(str(v))

    def is_valid_proportions(self) -> bool:
        if self.custom_proportions:
            total = sum(self.custom_proportions.values())
        else:
            total = sum(Decimal(str(item['percentage'])) for item in self.base_recipe_items)

        return total == Decimal('100.00')

    def get_requirements(self) -> List[IngredientRequirement]:
        requirements = []
        for item in self.base_recipe_items:
            ing_id = item['ingredient_id']

            if self.custom_proportions and ing_id in self.custom_proportions:
                percentage = self.custom_proportions[ing_id]
            else:
                percentage = Decimal(str(item['percentage']))

            weight_kg = self.quantity_kg * (percentage / Decimal('100.00'))

            requirements.append(IngredientRequirement(
                ingredient_id=ing_id,
                name=item['name'],
                is_in_bin=item['is_in_bin'],
                percentage=percentage,
                required_kg=weight_kg
            ))
        return requirements


class RecipeCostCalculator:
    """Pure recipe cost calculation from plain dictionaries and price maps."""

    def __init__(self, recipe_name: str, recipe_items: List[Dict], price_map: Dict[int, Decimal | None], recipe_id: int | None = None):
        self.recipe_name = recipe_name
        self.recipe_items = recipe_items
        self.price_map = price_map
        self.recipe_id = recipe_id

    def calculate_cost(self) -> RecipeCostInfo:
        total_cost = Decimal('0.00')
        item_costs = []
        missing_price_ingredients = []

        for item in self.recipe_items:
            price = self.price_map.get(item['ingredient_id'])
            percentage = Decimal(str(item['percentage']))
            quantity_per_ton_kg = Decimal('1000.00') * (percentage / Decimal('100.00'))

            if price is None or price <= Decimal('0.00000'):
                ingredient_name = item.get('ingredient_name', '')
                if ingredient_name:
                    missing_price_ingredients.append(ingredient_name)
                item_costs.append({
                    'ingredient_id': item['ingredient_id'],
                    'ingredient_name': ingredient_name,
                    'percentage': percentage,
                    'quantity_per_ton_kg': quantity_per_ton_kg,
                    'price_per_kg': None,
                    'price_per_ton': None,
                    'cost_per_kg': None,
                    'cost_per_ton': None,
                    'has_price': False,
                })
                continue

            cost_part = price * (percentage / Decimal('100.00'))
            total_cost += cost_part
            item_costs.append({
                'ingredient_id': item['ingredient_id'],
                'ingredient_name': item.get('ingredient_name', ''),
                'percentage': percentage,
                'quantity_per_ton_kg': quantity_per_ton_kg,
                'price_per_kg': price,
                'price_per_ton': price * Decimal('1000.00'),
                'cost_per_kg': cost_part,
                'cost_per_ton': cost_part * Decimal('1000.00'),
                'has_price': True,
            })

        return RecipeCostInfo(
            recipe_name=self.recipe_name,
            cost_per_kg=total_cost,
            recipe_id=self.recipe_id,
            item_costs=item_costs,
            missing_price_ingredients=missing_price_ingredients,
        )
