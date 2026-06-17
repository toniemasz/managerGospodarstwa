from decimal import Decimal
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeModel,
)


class FeedRepository:
    """
    Abstrakcja bazy danych. Tylko ta klasa ma prawo używać Django ORM
    (np. .objects.filter, .annotate, .save).
    """

    def __init__(self, farm=None):
        self.farm = farm

    def _filter_for_farm(self, **extra_filters):
        if self.farm is not None:
            extra_filters['farm'] = self.farm
        return extra_filters

    def _related_filter_for_farm(self, relation_name: str, **extra_filters):
        if self.farm is not None:
            extra_filters[f'{relation_name}__farm'] = self.farm
        return extra_filters

    def get_all_ingredients(self):
        return IngredientModel.objects.filter(**self._filter_for_farm()).order_by('name')

    def get_deliveries(self):
        filters = self._related_filter_for_farm('ingredient')
        return DeliveryModel.objects.select_related('ingredient').filter(**filters).order_by('-date', '-id')

    def get_delivery_aggregates(self) -> dict:
        """Zwraca słownik {ingredient_id: sum_of_deliveries}"""
        filters = self._related_filter_for_farm('ingredient')
        deliveries_agg = DeliveryModel.objects.filter(**filters).values('ingredient_id').annotate(total_kg=Sum('quantity_kg'))
        return {item['ingredient_id']: (item['total_kg'] or Decimal('0.00')) for item in deliveries_agg}

    def get_completed_productions(self):
        return ProductionModel.objects.filter(
            **self._related_filter_for_farm('recipe'),
            status=ProductionModel.Statuses.COMPLETED
        ).prefetch_related('recipe__items__ingredient')

    def get_production_for_processing(self, production_id: int, lock_for_update: bool = False):
        """Pobiera produkcję wraz z recepturą. Może zablokować wiersz w transakcji."""
        qs = ProductionModel.objects.select_related('recipe').prefetch_related('recipe__items__ingredient')
        if self.farm is not None:
            qs = qs.filter(recipe__farm=self.farm)
        if lock_for_update:
            qs = qs.select_for_update()
        return qs.get(pk=production_id)

    def save_production(self, production: ProductionModel):
        production.save()

    def get_recipes_with_items(self):
        """Tylko pobiera receptury z bazy z prefetch."""
        return RecipeModel.objects.filter(**self._filter_for_farm()).prefetch_related('items__ingredient').order_by('name')

    def recipe_exists(self, recipe_id: int) -> bool:
        return RecipeModel.objects.filter(**self._filter_for_farm(pk=recipe_id)).exists()

    def get_productions(self):
        return ProductionModel.objects.select_related('recipe').filter(
            **self._related_filter_for_farm('recipe')
        ).order_by('-date', '-time', '-id')

    def get_recipe_with_items(self, recipe_id: int):
        queryset = RecipeModel.objects.prefetch_related('items__ingredient')
        return get_object_or_404(queryset, **self._filter_for_farm(id=recipe_id))

    def get_productions_for_recipe(self, recipe_id: int):
        return ProductionModel.objects.filter(
            **self._related_filter_for_farm('recipe'),
            recipe_id=recipe_id,
        ).order_by('-date', '-time', '-id')

    def get_ingredient_prices_map(self) -> dict:
        """Pobiera ceny i zwraca jako prosty słownik {id: cena}."""
        filters = self._related_filter_for_farm('ingredient')
        configs = IngredientPriceConfigModel.objects.filter(**filters)
        return {config.ingredient_id: config.price_per_kg for config in configs}

    def get_latest_delivery_prices_map(self) -> dict:
        """Zwraca ceny z najnowszej dostawy każdego składnika."""
        filters = self._related_filter_for_farm('ingredient')
        deliveries = DeliveryModel.objects.filter(**filters).select_related('ingredient').order_by(
            'ingredient_id',
            '-date',
            '-id',
        )

        prices = {}
        for delivery in deliveries:
            if delivery.ingredient_id in prices:
                continue
            prices[delivery.ingredient_id] = delivery.price_per_kg or Decimal('0.00')
        return prices

    def get_latest_delivery_price_sources(self) -> dict:
        filters = self._related_filter_for_farm('ingredient')
        deliveries = DeliveryModel.objects.filter(**filters).select_related('ingredient').order_by(
            'ingredient_id',
            '-date',
            '-id',
        )

        sources = {}
        for delivery in deliveries:
            if delivery.ingredient_id in sources:
                continue
            sources[delivery.ingredient_id] = delivery
        return sources
