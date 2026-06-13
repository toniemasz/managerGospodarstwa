from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional


@dataclass
class InventoryItem:
    """Encja reprezentująca stan magazynowy pojedynczego składnika."""
    ingredient_id: int
    name: str
    total_delivered: Decimal
    total_used: Decimal
    is_in_bin: bool = False

    @property
    def current_stock(self) -> Decimal:
        return self.total_delivered - self.total_used


@dataclass
class RecipeCostInfo:
    """Encja reprezentująca wyliczony koszt produkcji z danej receptury."""
    recipe_name: str
    cost_per_kg: Decimal
    recipe_id: int | None = None
    item_costs: List[Dict] | None = None

    @property
    def cost_per_ton(self) -> Decimal:
        return self.cost_per_kg * Decimal('1000.00')


@dataclass
class IngredientRequirement:
    """Reprezentuje fizyczne zapotrzebowanie na dany surowiec w kg."""
    ingredient_id: int
    name: str
    is_in_bin: bool
    percentage: Decimal
    required_kg: Decimal


class ProductionCalculator:
    """
    Czysta encja domenowa.
    Odpowiada za reguły biznesowe: sumowanie do 100% i przeliczanie masy składników.
    """

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
    """
    Czysta encja domenowa do wyliczania kosztów receptury.
    Oczekuje czystych słowników Pythona, bez modeli Django.
    """

    def __init__(self, recipe_name: str, recipe_items: List[Dict], price_map: Dict[int, Decimal], recipe_id: int | None = None):
        self.recipe_name = recipe_name
        self.recipe_items = recipe_items
        self.price_map = price_map
        self.recipe_id = recipe_id

    def calculate_cost(self) -> RecipeCostInfo:
        total_cost = Decimal('0.00')
        item_costs = []

        for item in self.recipe_items:
            # Pobieramy cenę ze słownika (jeśli nie ma, to 0.00)
            price = self.price_map.get(item['ingredient_id'], Decimal('0.00'))
            percentage = Decimal(str(item['percentage']))

            # Obliczamy koszt z proporcji
            cost_part = price * (percentage / Decimal('100.00'))
            total_cost += cost_part
            item_costs.append({
                'ingredient_id': item['ingredient_id'],
                'ingredient_name': item.get('ingredient_name', ''),
                'percentage': percentage,
                'price_per_kg': price,
                'cost_per_kg': cost_part,
                'cost_per_ton': cost_part * Decimal('1000.00'),
            })

        return RecipeCostInfo(
            recipe_name=self.recipe_name,
            cost_per_kg=total_cost,
            recipe_id=self.recipe_id,
            item_costs=item_costs,
        )
