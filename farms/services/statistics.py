from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.urls import reverse

from costs.models import CostModel
from costs.services import CostService
from feed.models import DeliveryModel, ProductionModel
from feed.selectors.inventory import inventory_dashboard
from feed.selectors.production_costs import ProductionCostSelector
from sales.models import PigSaleModel


ZERO = Decimal("0.00")


def _safe_divide(numerator, denominator):
    numerator = numerator or ZERO
    denominator = denominator or ZERO
    if denominator == 0:
        return None
    return numerator / denominator


class FarmStatisticsService:
    """Jedno miejsce agregowania statystyk gospodarstwa."""

    def __init__(self, farm):
        self.farm = farm

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        sales = self._sales_queryset(date_from=date_from, date_to=date_to)
        costs = self._cost_queryset(date_from=date_from, date_to=date_to)
        feed = ProductionCostSelector(self.farm).calculate(date_from=date_from, date_to=date_to)
        sales_summary = self._sales_summary(sales)
        cost_summary = CostService.summarize(costs)
        timeline = self._timeline(sales=sales, costs=costs, feed=feed)
        profitability = self._profitability(sales_summary, cost_summary, feed, timeline)
        feed_efficiency = self._feed_efficiency(sales_summary, profitability, feed)
        production = self._production_summary(date_from=date_from, date_to=date_to, feed=feed)
        inventory = self._inventory_summary()

        return {
            "summary_cards": self._summary_cards(sales_summary, profitability, feed_efficiency),
            "sales": sales_summary,
            "costs": cost_summary,
            "feed": feed,
            "feed_efficiency": feed_efficiency,
            "production": production,
            "inventory": inventory,
            "profitability": profitability,
            "recipe_ranking": feed["recipe_ranking"],
            "production_details": feed["details"],
            "timeline": timeline,
            "chart_labels": [row["month"] for row in timeline],
            "chart_datasets": self._chart_datasets(timeline),
            "unavailable_indicators": self._unavailable_indicators(sales_summary, feed),
        }

    def _sales_queryset(self, *, date_from=None, date_to=None):
        queryset = PigSaleModel.objects.filter(farm=self.farm)
        if date_from:
            queryset = queryset.filter(sale_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(sale_date__lte=date_to)
        return queryset

    def _cost_queryset(self, *, date_from=None, date_to=None):
        queryset = CostModel.objects.filter(farm=self.farm).select_related("category")
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        return queryset

    @staticmethod
    def _sales_summary(sales) -> dict:
        totals = sales.aggregate(
            sale_count=Count("id"),
            gross=Sum("gross_value"),
            net=Sum("net_value"),
            quantity=Sum("quantity"),
            slaughter_weight=Sum("total_weight"),
            live_weight=Sum("live_weight"),
            vat=Sum("vat_value"),
            avg_meatiness=Avg("avg_meatiness_seurop"),
        )
        sold_quantity = totals["quantity"] or 0
        slaughter_weight = totals["slaughter_weight"] or ZERO
        live_weight = totals["live_weight"] or ZERO
        net = totals["net"] or ZERO
        gross = totals["gross"] or ZERO
        return {
            "sale_count": totals["sale_count"] or 0,
            "sold_quantity": sold_quantity,
            "slaughter_weight_kg": slaughter_weight,
            "live_weight_kg": live_weight,
            "net_sales": net,
            "gross_sales": gross,
            "vat_sales": totals["vat"] or ZERO,
            "average_price_per_kg": _safe_divide(net, slaughter_weight) or ZERO,
            "average_gross_per_live_kg": _safe_divide(gross, live_weight),
            "average_slaughter_weight_per_pig": _safe_divide(slaughter_weight, sold_quantity) or ZERO,
            "average_live_weight_per_pig": _safe_divide(live_weight, sold_quantity),
            "average_meatiness": totals["avg_meatiness"],
        }

    @staticmethod
    def _timeline(*, sales, costs, feed) -> list[dict]:
        rows = defaultdict(lambda: {
            "sales_net": ZERO,
            "sales_gross": ZERO,
            "feed_cost": ZERO,
            "additional_cost": ZERO,
            "production_kg": ZERO,
        })
        for sale in sales:
            if sale.sale_date:
                month = sale.sale_date.strftime("%Y-%m")
                rows[month]["sales_net"] += sale.net_value or ZERO
                rows[month]["sales_gross"] += sale.gross_value or ZERO
        for month, values in feed["monthly"].items():
            rows[month].update(values)
        for cost in costs:
            rows[cost.date.strftime("%Y-%m")]["additional_cost"] += cost.amount or ZERO
        for values in rows.values():
            values["result_net"] = values["sales_net"] - values["feed_cost"] - values["additional_cost"]
            values["result_gross"] = values["sales_gross"] - values["feed_cost"] - values["additional_cost"]
        return [{"month": month, **values} for month, values in sorted(rows.items())]

    @staticmethod
    def _profitability(sales_summary, cost_summary, feed, timeline) -> dict:
        total_cost = feed["total_cost"] + cost_summary["total"]
        net_sales = sales_summary["net_sales"]
        gross_sales = sales_summary["gross_sales"]
        live_weight = sales_summary["live_weight_kg"]
        return {
            "gross_sales": gross_sales,
            "net_sales": net_sales,
            "vat_sales": sales_summary["vat_sales"],
            "feed_cost": feed["total_cost"],
            "additional_cost": cost_summary["total"],
            "total_cost": total_cost,
            "net_result": net_sales - total_cost,
            "gross_result": gross_sales - total_cost,
            "feed_cost_per_live_kg": _safe_divide(feed["total_cost"], live_weight),
            "total_cost_per_live_kg": _safe_divide(total_cost, live_weight),
            "gross_per_live_kg": _safe_divide(gross_sales, live_weight),
            "timeline": timeline,
        }

    @staticmethod
    def _feed_efficiency(sales_summary, profitability, feed) -> dict:
        live_weight = sales_summary["live_weight_kg"]
        slaughter_weight = sales_summary["slaughter_weight_kg"]
        feed_quantity = feed["quantity_kg"]
        feed_cost = feed["total_cost"]
        net_sales = sales_summary["net_sales"]
        feed_to_live = _safe_divide(feed_quantity, live_weight)
        feed_share = _safe_divide(feed_cost, net_sales)
        return {
            "feed_quantity_kg": feed_quantity,
            "feed_cost": feed_cost,
            "average_feed_cost_per_kg": feed["average_cost_per_kg"],
            "average_feed_cost_per_ton": feed["average_cost_per_ton"],
            "feed_to_live_weight_ratio": feed_to_live,
            "feed_to_slaughter_weight_ratio": _safe_divide(feed_quantity, slaughter_weight),
            "live_weight_per_feed_kg": _safe_divide(live_weight, feed_quantity),
            "feed_cost_per_live_kg": profitability["feed_cost_per_live_kg"],
            "feed_cost_share_of_net_sales": feed_share,
            "feed_cost_share_of_net_sales_percent": feed_share * Decimal("100") if feed_share is not None else None,
            "has_closeout_data": bool(feed_quantity and live_weight),
        }

    def _production_summary(self, *, date_from=None, date_to=None, feed) -> dict:
        productions = ProductionModel.objects.filter(recipe__farm=self.farm)
        if date_from:
            productions = productions.filter(date__gte=date_from)
        if date_to:
            productions = productions.filter(date__lte=date_to)
        status_rows = {
            row["status"]: row
            for row in productions.values("status").annotate(
                count=Count("id"),
                quantity_kg=Sum("quantity_kg"),
            )
        }

        def status_value(status, field, default):
            row = status_rows.get(status, {})
            return row.get(field) or default

        completed_count = status_value(ProductionModel.Statuses.COMPLETED, "count", 0)
        completed_kg = feed["quantity_kg"]
        recipe_by_quantity = sorted(
            feed["recipe_ranking"],
            key=lambda row: row["quantity_kg"],
            reverse=True,
        )
        return {
            "total_count": productions.count(),
            "queued_count": status_value(ProductionModel.Statuses.QUEUED, "count", 0),
            "queued_kg": status_value(ProductionModel.Statuses.QUEUED, "quantity_kg", ZERO),
            "in_progress_count": status_value(ProductionModel.Statuses.STAGE_1_DONE, "count", 0),
            "in_progress_kg": status_value(ProductionModel.Statuses.STAGE_1_DONE, "quantity_kg", ZERO),
            "completed_count": completed_count,
            "completed_kg": completed_kg,
            "completed_t": completed_kg / Decimal("1000.00") if completed_kg else ZERO,
            "average_completed_batch_kg": _safe_divide(completed_kg, completed_count) or ZERO,
            "top_recipe_by_quantity": recipe_by_quantity[0] if recipe_by_quantity else None,
        }

    def _inventory_summary(self) -> dict:
        dashboard = inventory_dashboard(self.farm)
        inventory_rows = dashboard["inventory"]
        bin_stock = sum((item.current_stock for item in inventory_rows if item.is_in_bin), ZERO)
        bag_stock = sum((item.current_stock for item in inventory_rows if not item.is_in_bin), ZERO)
        latest_delivery = (
            DeliveryModel.objects
            .filter(ingredient__farm=self.farm)
            .select_related("ingredient")
            .order_by("-date", "-id")
            .first()
        )
        return {
            **dashboard,
            "ingredient_count": len(inventory_rows),
            "low_stock_count": len(dashboard["low_stock_alerts"]),
            "bin_stock_kg": bin_stock,
            "bag_stock_kg": bag_stock,
            "latest_delivery": latest_delivery,
        }

    @staticmethod
    def _summary_cards(sales_summary, profitability, feed_efficiency) -> list[dict]:
        net_result = profitability["net_result"]
        return [
            {
                "title": "Wynik netto",
                "value": net_result,
                "unit": "zł",
                "note": "Sprzedaż minus pasza i koszty",
                "tone": "is-danger" if net_result < 0 else "is-success",
            },
            {
                "title": "Sprzedaż netto",
                "value": sales_summary["net_sales"],
                "unit": "zł",
                "note": f"{sales_summary['sale_count']} dokumentów",
            },
            {
                "title": "Koszt paszy",
                "value": feed_efficiency["feed_cost"],
                "unit": "zł",
                "note": "Zakończone śrutowania FIFO",
            },
            {
                "title": "Pasza / waga żywa",
                "value": feed_efficiency["feed_to_live_weight_ratio"],
                "unit": "t/t",
                "note": "Przybliżony wskaźnik closeout",
            },
        ]

    @staticmethod
    def _chart_datasets(timeline) -> list[dict]:
        return [
            {
                "label": "Sprzedaż netto",
                "data": [float(row["sales_net"]) for row in timeline],
                "borderColor": "#2364aa",
                "backgroundColor": "rgba(35, 100, 170, .10)",
            },
            {
                "label": "Koszty łącznie",
                "data": [float(row["feed_cost"] + row["additional_cost"]) for row in timeline],
                "borderColor": "#c92a2a",
                "backgroundColor": "rgba(201, 42, 42, .08)",
            },
            {
                "label": "Wynik netto",
                "data": [float(row["result_net"]) for row in timeline],
                "borderColor": "#087f5b",
                "backgroundColor": "rgba(8, 127, 91, .08)",
            },
        ]

    @staticmethod
    def _unavailable_indicators(sales_summary, feed) -> list[dict]:
        items = []
        if sales_summary["live_weight_kg"] == 0:
            items.append({
                "title": "Pasza / waga żywa",
                "reason": "Brakuje wagi żywej w dokumentach sprzedaży.",
            })
        items.extend([
            {
                "title": "FCR przyrostowy",
                "reason": "Do dokładnego FCR potrzebna jest masa wejściowa lub przyrost grupy, nie tylko masa sprzedaży.",
            },
            {
                "title": "ADG i ADFI",
                "reason": "Średni dzienny przyrost i pobranie paszy wymagają dat wejścia/wyjścia grup oraz liczby dni tuczu.",
            },
            {
                "title": "Śmiertelność / brakowanie",
                "reason": "Aplikacja nie ma jeszcze ewidencji obsady grup tuczowych i upadków.",
            },
        ])
        if not feed["quantity_kg"]:
            items.insert(0, {
                "title": "Koszt paszy i FCR",
                "reason": "Brakuje zakończonych śrutowań w wybranym okresie.",
            })
        return items

    @staticmethod
    def statistic_links() -> list[dict]:
        return [
            {"label": "Opłacalność", "url": reverse("profitability")},
            {"label": "Sprzedaż", "url": reverse("sales_list")},
            {"label": "Śrutowanie", "url": reverse("feed_productions")},
            {"label": "Magazyn", "url": reverse("feed_inventory")},
        ]
