from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

from costs.models import CostModel
from costs.services import CostService
from feed.services.production_cost_service import ProductionCostService
from sales.models import PigSaleModel


class ProfitabilityAnalyticsService:
    def __init__(self, farm):
        self.farm = farm

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        sales = PigSaleModel.objects.filter(farm=self.farm)
        costs = CostModel.objects.filter(farm=self.farm)
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
            costs = costs.filter(date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
            costs = costs.filter(date__lte=date_to)

        sale_totals = sales.aggregate(
            gross=Sum("gross_value"),
            net=Sum("net_value"),
            quantity=Sum("quantity"),
            weight=Sum("total_weight"),
            live_weight=Sum("live_weight"),
            vat=Sum("vat_value"),
        )
        gross = sale_totals["gross"] or Decimal("0.00")
        net = sale_totals["net"] or Decimal("0.00")
        quantity = sale_totals["quantity"] or 0
        weight = sale_totals["weight"] or Decimal("0.00")
        live_weight = sale_totals["live_weight"] or Decimal("0.00")
        vat = sale_totals["vat"] or Decimal("0.00")

        feed = ProductionCostService(self.farm).calculate(date_from=date_from, date_to=date_to)
        cost_summary = CostService.summarize(costs)
        timeline = defaultdict(lambda: {
            "sales_net": Decimal("0.00"),
            "sales_gross": Decimal("0.00"),
            "feed_cost": Decimal("0.00"),
            "additional_cost": Decimal("0.00"),
            "production_kg": Decimal("0.00"),
        })
        for sale in sales:
            if sale.sale_date:
                timeline[sale.sale_date.strftime("%Y-%m")]["sales_net"] += sale.net_value or Decimal("0.00")
                timeline[sale.sale_date.strftime("%Y-%m")]["sales_gross"] += sale.gross_value or Decimal("0.00")
        for month, values in feed["monthly"].items():
            timeline[month].update(values)
        for cost in costs:
            timeline[cost.date.strftime("%Y-%m")]["additional_cost"] += cost.amount
        for values in timeline.values():
            values["result_net"] = values["sales_net"] - values["feed_cost"] - values["additional_cost"]
            values["result_gross"] = values["sales_gross"] - values["feed_cost"] - values["additional_cost"]

        timeline_rows = [{"month": month, **values} for month, values in sorted(timeline.items())]
        total_cost = feed["total_cost"] + cost_summary["total"]
        return {
            "gross_sales": gross,
            "net_sales": net,
            "vat_sales": vat,
            "sold_quantity": quantity,
            "live_weight_kg": live_weight,
            "slaughter_weight_kg": weight,
            "average_price_per_kg": net / weight if weight else Decimal("0.00"),
            "feed_quantity_kg": feed["quantity_kg"],
            "feed_cost": feed["total_cost"],
            "feed_cost_per_kg": feed["average_cost_per_kg"],
            "feed_cost_per_ton": feed["average_cost_per_ton"],
            "additional_cost": cost_summary["total"],
            "additional_cost_categories": cost_summary["categories"],
            "total_cost": total_cost,
            "net_result": net - total_cost,
            "gross_result": gross - total_cost,
            "feed_cost_per_live_kg": feed["total_cost"] / live_weight if live_weight else None,
            "total_cost_per_live_kg": total_cost / live_weight if live_weight else None,
            "gross_per_live_kg": gross / live_weight if live_weight else None,
            "feed_to_live_weight_ratio": feed["quantity_kg"] / live_weight if live_weight else None,
            "recipe_ranking": feed["recipe_ranking"],
            "production_details": feed["details"],
            "timeline": timeline_rows,
            "chart_labels": [row["month"] for row in timeline_rows],
            "chart_datasets": [
                {
                    "label": "Sprzedaż netto",
                    "data": [float(row["sales_net"]) for row in timeline_rows],
                    "borderColor": "#2364aa",
                    "backgroundColor": "rgba(35, 100, 170, .10)",
                },
                {
                    "label": "Koszty łącznie",
                    "data": [float(row["feed_cost"] + row["additional_cost"]) for row in timeline_rows],
                    "borderColor": "#c92a2a",
                    "backgroundColor": "rgba(201, 42, 42, .08)",
                },
                {
                    "label": "Wynik netto",
                    "data": [float(row["result_net"]) for row in timeline_rows],
                    "borderColor": "#087f5b",
                    "backgroundColor": "rgba(8, 127, 91, .08)",
                },
            ],
        }
