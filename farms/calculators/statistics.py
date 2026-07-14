from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


ZERO = Decimal("0.00")


def safe_divide(numerator, denominator):
    """Dzieli wartości raportowe bez tworzenia fałszywego zera przy braku mianownika."""
    numerator = numerator or ZERO
    denominator = denominator or ZERO
    if denominator == 0:
        return None
    return numerator / denominator


class StatisticsTimelineCalculator:
    """Buduje wspólny przebieg finansowy z gotowych agregatów domenowych."""

    @staticmethod
    def calculate(*, sales_monthly, additional_cost_monthly, feed_monthly) -> list[dict]:
        rows = defaultdict(lambda: {
            "sales_net": ZERO,
            "sales_gross": ZERO,
            "feed_cost": ZERO,
            "additional_cost": ZERO,
            "production_kg": ZERO,
        })
        for month, values in sales_monthly.items():
            rows[month].update(values)
        for month, values in feed_monthly.items():
            rows[month].update(values)
        for month, amount in additional_cost_monthly.items():
            rows[month]["additional_cost"] += amount
        for values in rows.values():
            values["result_net"] = values["sales_net"] - values["feed_cost"] - values["additional_cost"]
            values["result_gross"] = values["sales_gross"] - values["feed_cost"] - values["additional_cost"]
        return [{"month": month, **values} for month, values in sorted(rows.items())]


class ProfitabilityCalculator:
    """Liczy wskaźniki opłacalności bez zapytań i zależności od Django."""

    @staticmethod
    def calculate(*, sales, costs, feed, timeline) -> dict:
        total_cost = costs["total"]
        net_sales = sales["net_sales"]
        gross_sales = sales["gross_sales"]
        live_weight = sales["live_weight_kg"]
        additional_cost = costs["additional"]["total"]
        return {
            "gross_sales": gross_sales,
            "net_sales": net_sales,
            "vat_sales": sales["vat_sales"],
            "feed_cost": feed["total_cost"],
            "additional_cost": additional_cost,
            "total_cost": total_cost,
            "net_result": net_sales - total_cost,
            "gross_result": gross_sales - total_cost,
            "feed_cost_per_live_kg": safe_divide(feed["total_cost"], live_weight),
            "total_cost_per_live_kg": safe_divide(total_cost, live_weight),
            "gross_per_live_kg": safe_divide(gross_sales, live_weight),
            "timeline": timeline,
        }


class FeedEfficiencyCalculator:
    """Liczy wskaźniki łączące raport sprzedaży i raport paszowy."""

    @staticmethod
    def calculate(*, sales, feed, profitability=None) -> dict:
        live_weight = sales["live_weight_kg"]
        slaughter_weight = sales["slaughter_weight_kg"]
        feed_quantity = feed["quantity_kg"]
        feed_cost = feed["total_cost"]
        feed_to_live = safe_divide(feed_quantity, live_weight)
        feed_share = safe_divide(feed_cost, sales["net_sales"])
        feed_cost_per_live_kg = (
            profitability["feed_cost_per_live_kg"]
            if profitability is not None
            else safe_divide(feed_cost, live_weight)
        )
        return {
            "feed_quantity_kg": feed_quantity,
            "feed_cost": feed_cost,
            "average_feed_cost_per_kg": feed["average_cost_per_kg"],
            "average_feed_cost_per_ton": feed["average_cost_per_ton"],
            "feed_to_live_weight_ratio": feed_to_live,
            "feed_to_slaughter_weight_ratio": safe_divide(feed_quantity, slaughter_weight),
            "live_weight_per_feed_kg": safe_divide(live_weight, feed_quantity),
            "feed_cost_per_live_kg": feed_cost_per_live_kg,
            "feed_cost_share_of_net_sales": feed_share,
            "feed_cost_share_of_net_sales_percent": feed_share * Decimal("100") if feed_share is not None else None,
            "has_closeout_data": bool(feed_quantity and live_weight),
        }
