from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from feed.calculators.feed_cost import RecipeCostCalculator
from feed.models import ProductionModel, RecipeModel, RecipeVersionModel
from feed.selectors.inventory import (
    ingredients_for_farm,
    latest_delivery_price_sources,
    latest_delivery_prices_map,
)
from feed.selectors.productions import productions_for_farm, production_summary


def recipes_with_items(farm=None):
    filters = {"farm": farm} if farm is not None else {}
    return RecipeModel.objects.filter(**filters).prefetch_related("items__ingredient").order_by("name")


def recipe_list_context(farm) -> dict:
    costs = {cost.recipe_id: cost for cost in recipe_costs(farm)}
    recipe_cards = [
        {"recipe": recipe, "cost": costs.get(recipe.id)}
        for recipe in recipes_with_items(farm)
    ]
    return {"recipe_cards": recipe_cards}


def recipe_exists(farm, recipe_id: int) -> bool:
    filters = {"pk": recipe_id}
    if farm is not None:
        filters["farm"] = farm
    return RecipeModel.objects.filter(**filters).exists()


def recipe_with_items_or_404(farm, recipe_id: int):
    queryset = RecipeModel.objects.prefetch_related(
        "items__ingredient",
        "versions__items__ingredient",
    )
    filters = {"id": recipe_id}
    if farm is not None:
        filters["farm"] = farm
    return get_object_or_404(queryset, **filters)


def productions_for_recipe(farm, recipe_id: int):
    return productions_for_farm(farm).filter(recipe_id=recipe_id)


def recipe_version_for_farm_or_404(farm, recipe_pk, version_pk):
    return get_object_or_404(
        RecipeVersionModel.objects
        .select_related("recipe")
        .prefetch_related("items__ingredient"),
        pk=version_pk,
        recipe_id=recipe_pk,
        recipe__farm=farm,
    )


def recipe_version_detail_context(farm, recipe_pk, version_pk) -> dict:
    version = recipe_version_for_farm_or_404(farm, recipe_pk, version_pk)
    productions = productions_for_farm(farm).filter(recipe_version=version)
    return {
        "recipe": version.recipe,
        "version": version,
        "productions": productions[:50],
        "production_count": productions.count(),
        "completed_count": productions.filter(status=ProductionModel.Statuses.COMPLETED).count(),
    }


def recipe_costs(farm=None, price_overrides: dict[int, Decimal] | None = None):
    prices_map = latest_delivery_prices_map(farm)
    if price_overrides:
        prices_map.update(price_overrides)

    costs = []
    for recipe in recipes_with_items(farm):
        base_items = [
            {
                "ingredient_id": item.ingredient_id,
                "ingredient_name": item.ingredient.name,
                "percentage": item.percentage,
            }
            for item in recipe.items.all()
        ]
        costs.append(RecipeCostCalculator(
            recipe_id=recipe.id,
            recipe_name=recipe.name,
            recipe_items=base_items,
            price_map=prices_map,
        ).calculate_cost())
    return costs


def calculator_price_rows(farm=None, overrides: dict[int, Decimal] | None = None) -> list[dict]:
    prices_map = latest_delivery_prices_map(farm)
    sources = latest_delivery_price_sources(farm)
    if overrides:
        prices_map.update(overrides)

    rows = []
    for ingredient in ingredients_for_farm(farm):
        delivery = sources.get(ingredient.id)
        price = prices_map.get(ingredient.id)
        rows.append({
            "ingredient": ingredient,
            "price_per_kg": price,
            "source_date": delivery.date if delivery else None,
            "has_delivery": delivery is not None,
            "has_price": price is not None and price > Decimal("0.00000"),
        })
    return rows


def recipe_detail(farm, recipe_id: int, *, date_from=None, date_to=None, production_year: int | None = None) -> dict:
    recipe = recipe_with_items_or_404(farm, recipe_id)
    cost = _recipe_cost(recipe, farm)
    all_productions = productions_for_recipe(farm, recipe_id)
    recipe_versions = list(
        recipe.versions
        .prefetch_related("items__ingredient")
        .annotate(production_count=Count("productions"))
        .order_by("-version_number")
    )

    year = production_year or timezone.localdate().year
    available_years = [
        row.year for row in all_productions.filter(
            status=ProductionModel.Statuses.COMPLETED,
        ).dates("date", "year", order="DESC")
    ]
    if year not in available_years:
        available_years.insert(0, year)
    yearly_quantity_kg = all_productions.filter(
        status=ProductionModel.Statuses.COMPLETED,
        date__year=year,
    ).aggregate(quantity_kg=Sum("quantity_kg"))["quantity_kg"] or Decimal("0.00")

    productions = all_productions
    if date_from is not None:
        productions = productions.filter(date__gte=date_from)
    if date_to is not None:
        productions = productions.filter(date__lte=date_to)

    return {
        "recipe": recipe,
        "cost": cost,
        "productions": productions[:20],
        "stats": production_summary(productions),
        "yearly_production": {
            "year": year,
            "available_years": available_years,
            "quantity_kg": yearly_quantity_kg,
            "quantity_t": yearly_quantity_kg / Decimal("1000.00"),
        },
        "recipe_versions": recipe_versions,
    }


def _recipe_cost(recipe, farm=None):
    prices_map = latest_delivery_prices_map(farm)
    base_items = [
        {
            "ingredient_id": item.ingredient_id,
            "ingredient_name": item.ingredient.name,
            "percentage": item.percentage,
        }
        for item in recipe.items.all()
    ]
    return RecipeCostCalculator(
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        recipe_items=base_items,
        price_map=prices_map,
    ).calculate_cost()
