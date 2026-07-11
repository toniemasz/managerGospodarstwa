from __future__ import annotations

from common.cache import PROFITABILITY_TTL, cached_farm_value
from farms.services.statistics import FarmStatisticsService


class ProfitabilityAnalyticsService:
    def __init__(self, farm):
        self.farm = farm

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        return cached_farm_value(
            self.farm,
            "profitability",
            (date_from, date_to),
            timeout=PROFITABILITY_TTL,
            builder=lambda: self._calculate(date_from=date_from, date_to=date_to),
        )

    def _calculate(self, *, date_from=None, date_to=None) -> dict:
        stats = FarmStatisticsService(self.farm).calculate(date_from=date_from, date_to=date_to)
        sales = stats["sales"]
        feed = stats["feed"]
        additional_costs = stats["additional_costs"]
        profitability = stats["profitability"]
        feed_efficiency = stats["feed_efficiency"]
        return {
            "gross_sales": profitability["gross_sales"],
            "net_sales": profitability["net_sales"],
            "vat_sales": profitability["vat_sales"],
            "sold_quantity": sales["sold_quantity"],
            "live_weight_kg": sales["live_weight_kg"],
            "slaughter_weight_kg": sales["slaughter_weight_kg"],
            "average_price_per_kg": sales["average_price_per_kg"],
            "feed_quantity_kg": feed_efficiency["feed_quantity_kg"],
            "feed_cost": profitability["feed_cost"],
            "feed_cost_per_kg": feed_efficiency["average_feed_cost_per_kg"],
            "feed_cost_per_ton": feed_efficiency["average_feed_cost_per_ton"],
            "additional_cost": profitability["additional_cost"],
            "additional_cost_categories": additional_costs["categories"],
            "total_cost": profitability["total_cost"],
            "net_result": profitability["net_result"],
            "gross_result": profitability["gross_result"],
            "feed_cost_per_live_kg": profitability["feed_cost_per_live_kg"],
            "total_cost_per_live_kg": profitability["total_cost_per_live_kg"],
            "gross_per_live_kg": profitability["gross_per_live_kg"],
            "feed_to_live_weight_ratio": feed_efficiency["feed_to_live_weight_ratio"],
            "recipe_ranking": feed["recipe_ranking"],
            "production_details": feed["details"],
            "timeline": stats["timeline"],
            "chart_labels": stats["chart_labels"],
            "chart_datasets": stats["chart_datasets"],
        }
