from decimal import Decimal
from django.db.models import Sum
from feed.models import IngredientModel, DeliveryModel, ProductionModel


class FeedRepository:
    """
    Abstrakcja bazy danych. Tylko ta klasa ma prawo używać Django ORM
    (np. .objects.filter, .annotate, .save).
    """

    def get_all_ingredients(self):
        return IngredientModel.objects.all()

    def get_delivery_aggregates(self) -> dict:
        """Zwraca słownik {ingredient_id: sum_of_deliveries}"""
        deliveries_agg = DeliveryModel.objects.values('ingredient_id').annotate(total_kg=Sum('quantity_kg'))
        return {item['ingredient_id']: (item['total_kg'] or Decimal('0.00')) for item in deliveries_agg}

    def get_completed_productions(self):
        return ProductionModel.objects.filter(
            status=ProductionModel.Statuses.COMPLETED
        ).prefetch_related('recipe__items__ingredient')

    def get_production_for_processing(self, production_id: int, lock_for_update: bool = False):
        """Pobiera produkcję wraz z recepturą. Może zablokować wiersz w transakcji."""
        qs = ProductionModel.objects.select_related('recipe').prefetch_related('recipe__items__ingredient')
        if lock_for_update:
            qs = qs.select_for_update()
        return qs.get(pk=production_id)

    def save_production(self, production: ProductionModel):
        production.save()

    def get_recipes_with_items(self):
        """Tylko pobiera receptury z bazy z prefetch."""
        from feed.models import RecipeModel
        return RecipeModel.objects.prefetch_related('items__ingredient').all()

    def get_ingredient_prices_map(self) -> dict:
        """Pobiera ceny i zwraca jako prosty słownik {id: cena}."""
        from feed.models import IngredientPriceConfigModel
        configs = IngredientPriceConfigModel.objects.all()
        return {config.ingredient_id: config.price_per_kg for config in configs}

    def get_recipes_with_items(self):
        """Tylko pobiera receptury z bazy z prefetch."""
        from feed.models import RecipeModel
        return RecipeModel.objects.prefetch_related('items__ingredient').all()

    def get_ingredient_prices_map(self) -> dict:
        """Pobiera ceny i zwraca jako prosty słownik {id: cena}."""
        from feed.models import IngredientPriceConfigModel
        configs = IngredientPriceConfigModel.objects.all()
        return {config.ingredient_id: config.price_per_kg for config in configs}