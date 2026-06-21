from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from feed.models import ProductionModel
from feed.services.feed_management_service import FeedManagementService
from sales.models import PigSaleModel


class ProfitabilityAnalyticsService:
    def __init__(self, farm):
        self.farm = farm

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        sales = PigSaleModel.objects.filter(farm=self.farm)
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe").prefetch_related("recipe__items__ingredient")
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
            productions = productions.filter(date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
            productions = productions.filter(date__lte=date_to)

        sale_totals = sales.aggregate(
            gross=Sum("gross_value"),
            net=Sum("net_value"),
            quantity=Sum("quantity"),
            weight=Sum("total_weight"),
        )
        gross = sale_totals["gross"] or Decimal("0.00")
        net = sale_totals["net"] or Decimal("0.00")
        quantity = sale_totals["quantity"] or 0
        weight = sale_totals["weight"] or Decimal("0.00")

        feed_service = FeedManagementService(farm=self.farm)
        costs = {row.recipe_id: row for row in feed_service.get_recipe_costs()}
        feed_quantity = Decimal("0.00")
        feed_cost = Decimal("0.00")
        timeline = defaultdict(lambda: {"sales_net": Decimal("0.00"), "production_kg": Decimal("0.00")})
        for sale in sales:
            if sale.sale_date:
                timeline[sale.sale_date.strftime("%Y-%m")]["sales_net"] += sale.net_value or Decimal("0.00")
        for production in productions:
            feed_quantity += production.quantity_kg
            cost = costs.get(production.recipe_id)
            feed_cost += production.quantity_kg * (cost.cost_per_kg if cost else Decimal("0.00"))
            timeline[production.date.strftime("%Y-%m")]["production_kg"] += production.quantity_kg

        ranking = sorted(costs.values(), key=lambda item: item.cost_per_ton, reverse=True)
        return {
            "gross_sales": gross,
            "net_sales": net,
            "sold_quantity": quantity,
            "average_price_per_kg": net / weight if weight else Decimal("0.00"),
            "feed_quantity_kg": feed_quantity,
            "feed_cost": feed_cost,
            "feed_cost_per_ton": feed_cost / feed_quantity * Decimal("1000") if feed_quantity else Decimal("0.00"),
            "recipe_ranking": ranking,
            "timeline": [{"month": month, **values} for month, values in sorted(timeline.items())],
        }
