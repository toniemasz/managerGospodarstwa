from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from feed.models import DeliveryModel, ProductionModel
from feed.calculators.feed_cost import ProductionCalculator
from feed.selectors.recipe_requirements import recipe_item_dicts_for_production


class ProductionCostSelector:
    """Liczy koszt zrealizowanej paszy według daty produkcji i historycznych cen dostaw."""

    def __init__(self, farm):
        self.farm = farm

    @staticmethod
    def _requirements(production):
        return ProductionCalculator(
            quantity_kg=production.quantity_kg,
            base_recipe_items=recipe_item_dicts_for_production(production),
            custom_recipe_data=production.custom_recipe_data,
        ).get_requirements()

    def _price_at(self, ingredient_id, production_date) -> Decimal | None:
        delivery = DeliveryModel.objects.filter(
            ingredient_id=ingredient_id,
            ingredient__farm=self.farm,
            date__lte=production_date,
            price_per_kg__isnull=False,
            price_per_kg__gt=0,
        ).order_by("-date", "-id").first()
        if delivery:
            return delivery.price_per_kg
        fallback = DeliveryModel.objects.filter(
            ingredient_id=ingredient_id,
            ingredient__farm=self.farm,
            price_per_kg__isnull=False,
            price_per_kg__gt=0,
        ).order_by("date", "id").first()
        return fallback.price_per_kg if fallback else None

    def _legacy_components(self, production):
        components = []
        production_cost = Decimal("0.00")
        missing_prices = []
        for requirement in self._requirements(production):
            price = self._price_at(requirement.ingredient_id, production.date)
            component_cost = None
            if price is None:
                missing_prices.append(requirement.name)
            else:
                component_cost = requirement.required_kg * price
                production_cost += component_cost
            components.append({
                "ingredient_id": requirement.ingredient_id,
                "name": requirement.name,
                "quantity_kg": requirement.required_kg,
                "unit_price": price,
                "cost": component_cost,
                "delivery": None,
                "is_estimate": True,
            })
        return production_cost, components, missing_prices

    @staticmethod
    def _fifo_components(production):
        usages = list(production.ingredient_usages.all())
        if not usages:
            return None
        production_cost = Decimal("0.00")
        components = []
        for usage in usages:
            production_cost += usage.cost
            components.append({
                "ingredient_id": usage.ingredient_id,
                "name": usage.ingredient.name,
                "quantity_kg": usage.quantity_kg,
                "unit_price": usage.unit_price,
                "cost": usage.cost,
                "delivery": usage.delivery,
                "is_estimate": False,
            })
        return production_cost, components

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe", "recipe_version").prefetch_related(
            "recipe__items__ingredient",
            "recipe_version__items__ingredient",
            "ingredient_usages__ingredient",
            "ingredient_usages__delivery",
        )
        if date_from:
            productions = productions.filter(date__gte=date_from)
        if date_to:
            productions = productions.filter(date__lte=date_to)

        total_quantity = Decimal("0.00")
        total_cost = Decimal("0.00")
        recipe_totals = defaultdict(lambda: {"quantity_kg": Decimal("0.00"), "cost": Decimal("0.00")})
        monthly = defaultdict(lambda: {"production_kg": Decimal("0.00"), "feed_cost": Decimal("0.00")})
        details = []

        for production in productions:
            fifo_result = self._fifo_components(production)
            if fifo_result is None:
                production_cost, components, missing_prices = self._legacy_components(production)
                is_partial = bool(missing_prices)
                cost_note = (
                    "Częściowy koszt - brak ceny składników: " + ", ".join(missing_prices)
                    if missing_prices
                    else production.feed_cost_note
                )
            else:
                production_cost, components = fifo_result
                is_partial = production.feed_cost_is_partial
                cost_note = production.feed_cost_note

            total_quantity += production.quantity_kg
            total_cost += production_cost
            recipe_row = recipe_totals[(production.recipe_id, production.recipe.name)]
            recipe_row["quantity_kg"] += production.quantity_kg
            recipe_row["cost"] += production_cost
            month_row = monthly[production.date.strftime("%Y-%m")]
            month_row["production_kg"] += production.quantity_kg
            month_row["feed_cost"] += production_cost
            details.append({
                "production": production,
                "date": production.date,
                "recipe_name": production.recipe.name,
                "cost": production_cost,
                "total_cost": production_cost,
                "cost_per_kg": production_cost / production.quantity_kg if production.quantity_kg else Decimal("0.00"),
                "quantity_kg": production.quantity_kg,
                "components": components,
                "is_partial": is_partial,
                "cost_note": cost_note,
            })

        ranking = []
        for (recipe_id, recipe_name), values in recipe_totals.items():
            cost_per_kg = values["cost"] / values["quantity_kg"] if values["quantity_kg"] else Decimal("0.00")
            ranking.append({
                "recipe_id": recipe_id,
                "recipe_name": recipe_name,
                **values,
                "cost_per_kg": cost_per_kg,
                "cost_per_ton": cost_per_kg * Decimal("1000"),
            })
        ranking.sort(key=lambda row: row["cost_per_ton"], reverse=True)
        return {
            "quantity_kg": total_quantity,
            "total_cost": total_cost,
            "average_cost_per_kg": total_cost / total_quantity if total_quantity else Decimal("0.00"),
            "average_cost_per_ton": total_cost / total_quantity * Decimal("1000") if total_quantity else Decimal("0.00"),
            "recipe_ranking": ranking,
            "monthly": dict(monthly),
            "details": details,
        }
