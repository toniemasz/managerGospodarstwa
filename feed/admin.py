from django.contrib import admin
from .models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    ProductionIngredientUsageModel,
    RecipeItemModel,
    RecipeModel,
    RecipeVersionItemModel,
    RecipeVersionModel,
    InventoryMovementModel,
)
from feed.actions.inventory import InventoryActions


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
    list_display = ('date', 'ingredient', 'quantity_kg', 'remaining_quantity_kg', 'price_per_kg')
    list_filter = ('ingredient__farm', 'ingredient')
    search_fields = ('ingredient__name', 'ingredient__farm__name')

    def save_model(self, request, obj, form, change):
        previous_ingredient_id = None
        if change and obj.pk:
            previous_ingredient_id = DeliveryModel.objects.filter(pk=obj.pk).values_list("ingredient_id", flat=True).first()
        super().save_model(request, obj, form, change)
        if previous_ingredient_id and previous_ingredient_id != obj.ingredient_id:
            InventoryMovementModel.objects.filter(
                movement_type=InventoryMovementModel.Types.DELIVERY,
                source_model=obj._meta.label,
                source_id=str(obj.pk),
            ).delete()
        InventoryActions(obj.ingredient.farm).sync_delivery(obj, user=request.user)

    def delete_model(self, request, obj):
        InventoryActions(obj.ingredient.farm).remove_delivery(obj)
        super().delete_model(request, obj)


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


@admin.register(RecipeVersionModel)
class RecipeVersionAdmin(admin.ModelAdmin):
    list_display = ('recipe', 'version_number', 'is_current', 'valid_from', 'valid_to', 'created_by')
    list_filter = ('recipe__farm', 'is_current')
    search_fields = ('recipe__name', 'recipe__farm__name')


@admin.register(RecipeVersionItemModel)
class RecipeVersionItemAdmin(admin.ModelAdmin):
    list_display = ('recipe_version', 'ingredient', 'percentage')
    list_filter = ('recipe_version__recipe__farm', 'recipe_version')
    search_fields = ('recipe_version__recipe__name', 'ingredient__name')


@admin.register(ProductionModel)
class ProductionAdmin(admin.ModelAdmin):
    list_display = ('date', 'time', 'recipe', 'recipe_version', 'quantity_kg', 'status', 'feed_cost_total', 'feed_cost_per_kg')
    list_filter = ('recipe__farm', 'status', 'recipe_version')
    search_fields = ('recipe__name', 'recipe__farm__name')


@admin.register(InventoryMovementModel)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = ('movement_date', 'farm', 'ingredient', 'movement_type', 'quantity_kg', 'source_model')
    list_filter = ('farm', 'movement_type')
    search_fields = ('ingredient__name', 'note', 'source_id')


@admin.register(ProductionIngredientUsageModel)
class ProductionIngredientUsageAdmin(admin.ModelAdmin):
    list_display = ('production', 'ingredient', 'delivery', 'quantity_kg', 'unit_price', 'cost')
    list_filter = ('farm', 'ingredient')
    search_fields = ('production__recipe__name', 'ingredient__name', 'delivery__id')
