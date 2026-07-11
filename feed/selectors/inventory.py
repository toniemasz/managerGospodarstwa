from decimal import Decimal

from feed.calculators.feed_cost import InventoryItem
from feed.models import DeliveryModel, IngredientModel, InventoryMovementModel
from common.cache import INVENTORY_TTL, cached_farm_value


def ingredients_for_farm(farm):
    return IngredientModel.objects.filter(farm=farm).order_by("name")


def deliveries_for_farm(farm):
    queryset = DeliveryModel.objects.select_related("ingredient").filter(ingredient__farm=farm)
    return queryset.order_by("-date", "-id")


def latest_delivery_prices_map(farm) -> dict[int, Decimal]:
    prices = {}
    for delivery in _latest_delivery_candidates(farm):
        if delivery.ingredient_id in prices:
            continue
        if delivery.price_per_kg is not None and delivery.price_per_kg > Decimal("0.00000"):
            prices[delivery.ingredient_id] = delivery.price_per_kg
    return prices


def latest_delivery_price_sources(farm) -> dict[int, DeliveryModel]:
    sources = {}
    for delivery in _latest_delivery_candidates(farm):
        if delivery.ingredient_id not in sources:
            sources[delivery.ingredient_id] = delivery
    return sources


def _latest_delivery_candidates(farm):
    queryset = DeliveryModel.objects.select_related("ingredient").filter(ingredient__farm=farm)
    return queryset.order_by("ingredient_id", "-date", "-id")


def movement_totals(farm) -> dict[int, tuple[Decimal, Decimal]]:
    queryset = InventoryMovementModel.objects.filter(farm=farm)

    totals: dict[int, tuple[Decimal, Decimal]] = {}
    for ingredient_id, quantity in queryset.values_list("ingredient_id", "quantity_kg"):
        delivered, consumed = totals.get(ingredient_id, (Decimal("0.00"), Decimal("0.00")))
        if quantity > 0:
            delivered += quantity
        else:
            consumed += abs(quantity)
        totals[ingredient_id] = (delivered, consumed)
    return totals


def inventory_dashboard(farm) -> dict:
    return cached_farm_value(
        farm,
        "inventory",
        (),
        timeout=INVENTORY_TTL,
        builder=lambda: _build_inventory_dashboard(farm),
    )


def _build_inventory_dashboard(farm) -> dict:
    totals = movement_totals(farm)
    inventory_state = []

    for ingredient in ingredients_for_farm(farm):
        total_delivered, total_consumed = totals.get(
            ingredient.id,
            (Decimal("0.00"), Decimal("0.00")),
        )
        inventory_state.append(InventoryItem(
            ingredient_id=ingredient.id,
            name=ingredient.name,
            is_in_bin=ingredient.is_in_bin,
            low_stock_threshold_kg=ingredient.low_stock_threshold_kg,
            total_delivered=total_delivered,
            total_used=total_consumed,
        ))

    low_stock = [item for item in inventory_state if item.is_low_stock]
    total_inventory_kg = sum((item.current_stock for item in inventory_state), Decimal("0.00"))

    return {
        "inventory": inventory_state,
        "low_stock_alerts": low_stock,
        "total_inventory_kg": total_inventory_kg,
        "total_inventory_t": total_inventory_kg / Decimal("1000.00"),
    }


def inventory_movements(farm, *, movement_type="", date_from=None, date_to=None):
    movements = InventoryMovementModel.objects.filter(farm=farm).select_related("ingredient")
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if date_from:
        movements = movements.filter(movement_date__gte=date_from)
    if date_to:
        movements = movements.filter(movement_date__lte=date_to)
    return movements


def inventory_page_context(farm, *, movement_type="", date_from=None, date_to=None) -> dict:
    context = inventory_dashboard(farm)
    movements = inventory_movements(
        farm,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
    )
    context.update({
        "deliveries": deliveries_for_farm(farm),
        "movements": movements[:50],
        "movement_types": InventoryMovementModel.Types.choices,
    })
    return context
