from __future__ import annotations

from feed.models import ProductionModel


def recipe_item_dicts_for_production(production: ProductionModel) -> list[dict]:
    if production.recipe_version_id:
        version_items = list(
            production.recipe_version.items.select_related('ingredient').order_by('ingredient__name', 'id')
        )
        if version_items:
            return [
                {
                    'ingredient_id': item.ingredient_id,
                    'name': item.ingredient.name,
                    'ingredient_name': item.ingredient.name,
                    'is_in_bin': item.ingredient.is_in_bin,
                    'percentage': item.percentage,
                }
                for item in version_items
            ]

    return [
        {
            'ingredient_id': item.ingredient_id,
            'name': item.ingredient.name,
            'ingredient_name': item.ingredient.name,
            'is_in_bin': item.ingredient.is_in_bin,
            'percentage': item.percentage,
        }
        for item in production.recipe.items.select_related('ingredient').order_by('ingredient__name', 'id')
    ]
