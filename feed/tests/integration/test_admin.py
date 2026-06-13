from django.contrib import admin

from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)


def test_feed_models_are_registered_in_admin():
    for model in [
        IngredientModel,
        DeliveryModel,
        IngredientPriceConfigModel,
        RecipeModel,
        RecipeItemModel,
        ProductionModel,
    ]:
        assert model in admin.site._registry
