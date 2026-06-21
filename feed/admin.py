from django.contrib import admin
from .models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
    InventoryMovementModel,
)


@admin.register(IngredientModel)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ('name', 'farm', 'is_in_bin', 'low_stock_threshold_kg')
    list_filter = ('farm', 'is_in_bin')
    search_fields = ('name', 'farm__name', 'farm__owner__username')


@admin.register(RecipeModel)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('name', 'farm', 'created_at')
    list_filter = ('farm',)
    search_fields = ('name', 'farm__name', 'farm__owner__username')


@admin.register(DeliveryModel)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ('date', 'ingredient', 'quantity_kg', 'price_per_kg')
    list_filter = ('ingredient__farm', 'ingredient')
    search_fields = ('ingredient__name', 'ingredient__farm__name')


@admin.register(IngredientPriceConfigModel)
class IngredientPriceConfigAdmin(admin.ModelAdmin):
    list_display = ('ingredient', 'price_per_kg')
    list_filter = ('ingredient__farm',)
    search_fields = ('ingredient__name', 'ingredient__farm__name')


@admin.register(RecipeItemModel)
class RecipeItemAdmin(admin.ModelAdmin):
    list_display = ('recipe', 'ingredient', 'percentage')
    list_filter = ('recipe__farm', 'recipe')
    search_fields = ('recipe__name', 'ingredient__name')


@admin.register(ProductionModel)
class ProductionAdmin(admin.ModelAdmin):
    list_display = ('date', 'time', 'recipe', 'quantity_kg', 'status')
    list_filter = ('recipe__farm', 'status')
    search_fields = ('recipe__name', 'recipe__farm__name')


@admin.register(InventoryMovementModel)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ('movement_date', 'farm', 'ingredient', 'movement_type', 'quantity_kg', 'source_model')
    list_filter = ('farm', 'movement_type')
    search_fields = ('ingredient__name', 'note', 'source_id')
