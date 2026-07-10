from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from farms.services.settings_service import get_farm_settings
from feed.calculators.feed_cost import ProductionCalculator
from feed.domain.rules import DEFAULT_PRODUCTION_QUANTITY_KG
from feed.models import ProductionModel, RecipeModel
from feed.selectors.inventory import inventory_dashboard, latest_delivery_prices_map
from feed.selectors.recipe_requirements import recipe_item_dicts_for_production


def productions_for_farm(farm=None):
    queryset = ProductionModel.objects.select_related("recipe", "recipe_version")
    if farm is not None:
        queryset = queryset.filter(recipe__farm=farm)
    return queryset.order_by("-date", "-time", "-id")


def production_list_context(farm, *, status="", date_from=None, date_to=None) -> dict:
    productions = productions_for_farm(farm)
    if status:
        productions = productions.filter(status=status)
    if date_from:
        productions = productions.filter(date__gte=date_from)
    if date_to:
        productions = productions.filter(date__lte=date_to)
    return {
        "productions": productions,
        "production_statuses": ProductionModel.Statuses.choices,
    }


def production_for_processing(farm, production_id: int, *, lock_for_update: bool = False):
    queryset = ProductionModel.objects.select_related("recipe", "recipe_version").prefetch_related(
        "recipe__items__ingredient",
        "recipe_version__items__ingredient",
    )
    if farm is not None:
        queryset = queryset.filter(recipe__farm=farm)
    if lock_for_update:
        queryset = queryset.select_for_update()
    return queryset.get(pk=production_id)


def production_or_404(farm, production_id: int):
    return get_object_or_404(ProductionModel, pk=production_id, recipe__farm=farm)


def default_production_quantity(farm=None) -> Decimal:
    if farm is None:
        return DEFAULT_PRODUCTION_QUANTITY_KG
    return get_farm_settings(farm).default_production_quantity_kg


def default_production_initial(farm, *, selected_recipe=None, current_datetime=None) -> dict:
    current_datetime = current_datetime or timezone.now()
    initial = {
        "quantity_kg": default_production_quantity(farm),
        "date": current_datetime.date(),
        "time": current_datetime.strftime("%H:%M"),
    }
    if selected_recipe and _recipe_exists_for_farm(farm, selected_recipe):
        initial["recipe"] = selected_recipe
    return initial


def _recipe_exists_for_farm(farm, recipe_id) -> bool:
    filters = {"pk": recipe_id}
    if farm is not None:
        filters["farm"] = farm
    return RecipeModel.objects.filter(**filters).exists()


def _calculator_for_production(production) -> ProductionCalculator:
    return ProductionCalculator(
        quantity_kg=production.quantity_kg,
        base_recipe_items=recipe_item_dicts_for_production(production),
        custom_recipe_data=production.custom_recipe_data,
    )


def validate_production_capacity(farm, production_id: int) -> tuple[bool, list[str]]:
    production = production_for_processing(farm, production_id)
    inventory_state = inventory_dashboard(farm)["inventory"]
    inventory_map = {item.ingredient_id: item.current_stock for item in inventory_state}
    name_map = {item.ingredient_id: item.name for item in inventory_state}

    errors = []
    for requirement in _calculator_for_production(production).get_requirements():
        available = inventory_map.get(requirement.ingredient_id, Decimal("0.00"))
        if requirement.required_kg > available:
            ingredient_name = name_map.get(requirement.ingredient_id, requirement.name)
            errors.append(
                f"Brakuje {requirement.required_kg - available:.2f} kg składnika "
                f"'{ingredient_name}' (Dostępne: {available:.2f} kg)"
            )

    return len(errors) == 0, errors


def production_details_for_stages(farm, production_id: int) -> dict:
    production = production_for_processing(farm, production_id)
    price_map = latest_delivery_prices_map(farm)
    sorted_requirements = sorted(_calculator_for_production(production).get_requirements(), key=lambda item: item.name)

    enriched_requirements = []
    total_cost = Decimal("0.00")
    missing_price_ingredients = []
    for requirement in sorted_requirements:
        price = price_map.get(requirement.ingredient_id)
        cost = None
        if price is None or price <= Decimal("0.00000"):
            missing_price_ingredients.append(requirement.name)
        else:
            cost = requirement.required_kg * price
            total_cost += cost
        enriched_requirements.append({
            "id": requirement.ingredient_id,
            "name": requirement.name,
            "is_in_bin": requirement.is_in_bin,
            "percentage": requirement.percentage,
            "weight_kg": requirement.required_kg,
            "price_per_kg": price,
            "price_per_ton": price * Decimal("1000.00") if price is not None and price > Decimal("0.00000") else None,
            "cost": cost,
            "has_price": price is not None and price > Decimal("0.00000"),
        })

    stage1_items = [item for item in enriched_requirements if item["is_in_bin"]]
    stage2_items = [item for item in enriched_requirements if not item["is_in_bin"]]
    cost_per_kg = (total_cost / production.quantity_kg) if production.quantity_kg else Decimal("0.00")

    return {
        "production": production,
        "stage1_items": stage1_items,
        "stage2_items": stage2_items,
        "all_items": enriched_requirements,
        "production_cost": {
            "total_cost": total_cost,
            "cost_per_kg": cost_per_kg,
            "cost_per_ton": cost_per_kg * Decimal("1000.00"),
            "is_complete": not missing_price_ingredients,
            "missing_price_ingredients": missing_price_ingredients,
        },
    }


def production_counts_for_version(farm, version):
    productions = ProductionModel.objects.filter(recipe_version=version, recipe__farm=farm)
    return {
        "assigned": productions.count(),
        "completed": productions.filter(status=ProductionModel.Statuses.COMPLETED).count(),
        "custom": productions.filter(
            status=ProductionModel.Statuses.COMPLETED,
            custom_recipe_data__isnull=False,
        ).count(),
    }


def production_summary(productions):
    aggregate = productions.aggregate(
        total_count=Count("id"),
        total_planned_kg=Sum("quantity_kg"),
    )
    completed = productions.filter(status=ProductionModel.Statuses.COMPLETED).aggregate(
        count=Count("id"),
        quantity_kg=Sum("quantity_kg"),
        feed_cost=Sum("feed_cost_total"),
    )
    queued = productions.filter(status=ProductionModel.Statuses.QUEUED).aggregate(
        count=Count("id"),
        quantity_kg=Sum("quantity_kg"),
    )
    in_progress = productions.filter(status=ProductionModel.Statuses.STAGE_1_DONE).aggregate(
        count=Count("id"),
        quantity_kg=Sum("quantity_kg"),
    )
    return {
        "total_count": aggregate["total_count"] or 0,
        "total_planned_kg": aggregate["total_planned_kg"] or Decimal("0.00"),
        "completed_count": completed["count"] or 0,
        "completed_kg": completed["quantity_kg"] or Decimal("0.00"),
        "completed_t": (completed["quantity_kg"] or Decimal("0.00")) / Decimal("1000.00"),
        "completed_cost": completed["feed_cost"] or Decimal("0.00"),
        "queued_count": queued["count"] or 0,
        "queued_kg": queued["quantity_kg"] or Decimal("0.00"),
        "in_progress_count": in_progress["count"] or 0,
        "in_progress_kg": in_progress["quantity_kg"] or Decimal("0.00"),
    }
