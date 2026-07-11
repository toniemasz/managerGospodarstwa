from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from feed.models import ProductionModel


class ProductionCostSelector:
    """Prezentuje produkcje paszy, pobierając ich kwoty z rejestru kosztów."""

    def __init__(self, farm):
        self.farm = farm

    @staticmethod
    def _fifo_components(production):
        usages = list(production.ingredient_usages.all())
        components = []
        for usage in usages:
            components.append({
                "ingredient_id": usage.ingredient_id,
                "name": usage.ingredient.name,
                "quantity_kg": usage.quantity_kg,
                "unit_price": usage.unit_price,
                "cost": usage.cost,
                "delivery": usage.delivery,
                "is_estimate": False,
            })
        return components

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe", "recipe_version", "cost_entry").prefetch_related(
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
            cost_entry = getattr(production, "cost_entry", None)
            production_cost = cost_entry.amount if cost_entry is not None else Decimal("0.00")
            components = self._fifo_components(production)
            is_partial = production.feed_cost_is_partial or cost_entry is None
            cost_note = production.feed_cost_note
            if cost_entry is None:
                cost_note = "Brak zapisanego kosztu produkcji paszy. Wymagana synchronizacja FIFO."

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
