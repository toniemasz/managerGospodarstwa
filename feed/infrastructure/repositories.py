from decimal import Decimal
from django.db.models import Sum, F, DecimalField
from feed.models import IngredientModel, DeliveryModel, ProductionModel, RecipeModel, IngredientPriceConfigModel
from feed.domain.entities import InventoryItem, RecipeCostInfo


class FeedRepository:

    def get_inventory_state(self) -> list[InventoryItem]:
        ingredients = IngredientModel.objects.all()
        inventory = []

        for ing in ingredients:
            # Suma dostaw
            delivered = DeliveryModel.objects.filter(ingredient=ing).aggregate(
                total=Sum('quantity_kg')
            )['total'] or Decimal('0.00')

        
            used = Decimal('0.00')
            productions = ProductionModel.objects.filter(recipe__items__ingredient=ing).annotate(
                percentage=F('recipe__items__percentage')
            )

            for prod in productions:
                used += (prod.quantity_kg * (prod.percentage / Decimal('100.00')))

            inventory.append(InventoryItem(
                ingredient_id=ing.id,
                ingredient_name=ing.name,
                total_delivered=delivered,
                total_used=used
            ))

        return inventory

    def get_recipe_costs(self) -> list[RecipeCostInfo]:
        recipes = RecipeModel.objects.prefetch_related('items__ingredient__price_config').all()
        costs = []

        for recipe in recipes:
            total_cost_per_kg = Decimal('0.00')
            for item in recipe.items.all():
                try:
                    price = item.ingredient.price_config.price_per_kg
                except IngredientPriceConfigModel.DoesNotExist:
                    price = Decimal('0.00')

                percentage = item.percentage / Decimal('100.00')
                total_cost_per_kg += (price * percentage)

            costs.append(RecipeCostInfo(
                recipe_name=recipe.name,
                cost_per_kg=total_cost_per_kg
            ))
        return costs