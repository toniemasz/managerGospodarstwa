from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.urls import reverse

from costs.services import CostReportingService
from common.cache import STATISTICS_TTL, cached_farm_value
from feed.services.reporting import FeedReportingService, InventoryReportingService
from sales.services.reporting import SalesReportingService
from sows.services.reporting import MortalityReportingService


ZERO = Decimal("0.00")


def _safe_divide(numerator, denominator):
    numerator = numerator or ZERO
    denominator = denominator or ZERO
    if denominator == 0:
        return None
    return numerator / denominator


class FarmStatisticsService:
    """Jedno miejsce agregowania statystyk gospodarstwa."""

    SECTION_KEYS = ("profitability", "sales", "mortality", "feed", "inventory", "costs")

    def __init__(self, farm):
        self.farm = farm

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        return cached_farm_value(
            self.farm,
            "statistics",
            (date_from, date_to),
            timeout=STATISTICS_TTL,
            builder=lambda: self._calculate(date_from=date_from, date_to=date_to),
        )

    def _calculate(self, *, date_from=None, date_to=None) -> dict:
        sales_summary = SalesReportingService(self.farm).summary(date_from=date_from, date_to=date_to)
        cost_summary = CostReportingService(self.farm).summary(date_from=date_from, date_to=date_to)
        additional_cost_summary = cost_summary["additional"]
        feed = FeedReportingService(self.farm).summary(date_from=date_from, date_to=date_to)
        timeline = self._timeline(
            sales_monthly=sales_summary["monthly"],
            additional_cost_monthly=cost_summary["additional_monthly"],
            feed=feed,
        )
        profitability = self._profitability(
            sales_summary,
            cost_summary,
            additional_cost_summary,
            feed,
            timeline,
        )
        feed_efficiency = self._feed_efficiency(sales_summary, profitability, feed)
        production = feed["production"]
        inventory = InventoryReportingService(self.farm).summary()
        mortality = MortalityReportingService(self.farm).summary(date_from=date_from, date_to=date_to)

        return {
            "summary_cards": self._summary_cards(sales_summary, profitability, feed_efficiency),
            "sales": sales_summary,
            "costs": cost_summary,
            "additional_costs": additional_cost_summary,
            "feed": feed,
            "feed_efficiency": feed_efficiency,
            "production": production,
            "inventory": inventory,
            "mortality": mortality,
            "profitability": profitability,
            "recipe_ranking": feed["recipe_ranking"],
            "production_details": feed["details"],
            "timeline": timeline,
            "chart_labels": [row["month"] for row in timeline],
            "chart_datasets": self._chart_datasets(timeline),
            "unavailable_indicators": self._unavailable_indicators(sales_summary, feed),
        }

    def section_context(self, section, *, date_from=None, date_to=None) -> dict:
        """Zwraca prezentacyjny kontrakt pojedynczej sekcji z tego samego wyniku obliczeń."""
        if section not in self.SECTION_KEYS:
            raise ValueError("Nieznana sekcja statystyk.")
        data = self.calculate(date_from=date_from, date_to=date_to)
        builders = {
            "profitability": self._profitability_section,
            "sales": self._sales_section,
            "mortality": self._mortality_section,
            "feed": self._feed_section,
            "inventory": self._inventory_section,
            "costs": self._costs_section,
        }
        return {**data, **builders[section](data), "active_section": section}

    @staticmethod
    def _card(title, value, unit="", note="", tone=""):
        return {"title": title, "value": value, "unit": unit, "note": note, "tone": tone}

    @classmethod
    def _profitability_section(cls, data):
        values = data["profitability"]
        return {
            "section_title": "Opłacalność",
            "section_description": "Sprzedaż, koszty i wynik gospodarstwa w wybranym roku.",
            "section_cards": [
                cls._card("Wynik netto", values["net_result"], "zł", tone="is-success" if values["net_result"] >= 0 else "is-danger"),
                cls._card("Sprzedaż netto", values["net_sales"], "zł"),
                cls._card("Koszty razem", values["total_cost"], "zł"),
                cls._card("Koszt/kg żywej", values["total_cost_per_live_kg"], "zł/kg"),
                cls._card("Sprzedaż brutto/kg żywej", values["gross_per_live_kg"], "zł/kg"),
                cls._card("Koszt paszy", values["feed_cost"], "zł"),
                cls._card("Pozostałe koszty", values["additional_cost"], "zł"),
                cls._card("Wynik brutto", values["gross_result"], "zł"),
            ],
            "section_rows": data["timeline"],
            "row_kind": "timeline",
        }

    @classmethod
    def _sales_section(cls, data):
        values = data["sales"]
        return {
            "section_title": "Sprzedaż",
            "section_description": "Wolumen, masa i wartości dokumentów sprzedaży.",
            "section_cards": [
                cls._card("Sprzedane sztuki", values["sold_quantity"], "szt."),
                cls._card("Dokumenty", values["sale_count"]),
                cls._card("Sprzedaż netto", values["net_sales"], "zł"),
                cls._card("Sprzedaż brutto", values["gross_sales"], "zł"),
                cls._card("VAT", values["vat_sales"], "zł"),
                cls._card("Waga żywa", values["live_weight_kg"], "kg"),
                cls._card("Waga poubojowa", values["slaughter_weight_kg"], "kg"),
                cls._card("Średnia cena/kg", values["average_price_per_kg"], "zł/kg"),
                cls._card("Średnia waga poubojowa/szt.", values["average_slaughter_weight_per_pig"], "kg"),
                cls._card("Średnia waga żywa/szt.", values["average_live_weight_per_pig"], "kg"),
                cls._card("Średnia mięsność", values["average_meatiness"], "%"),
            ],
            "section_rows": data["timeline"],
            "row_kind": "timeline",
        }

    @classmethod
    def _mortality_section(cls, data):
        values = data["mortality"]
        return {
            "section_title": "Upadki i stan",
            "section_description": "Rozdzielone straty przed i po odsadzeniu oraz bieżący stan.",
            "section_cards": [
                cls._card("Maciory", values["sow_deaths"], "szt."),
                cls._card("Przed odsadzeniem", values["pre_weaning_deaths"], "szt."),
                cls._card("Prosiaki", values["piglet_deaths"], "szt."),
                cls._card("Warchlaki", values["weaner_deaths"], "szt."),
                cls._card("Tuczniki", values["finisher_deaths"], "szt."),
                cls._card("Nieokreślone", values["unspecified_post_weaning_deaths"], "szt."),
                cls._card("Po odsadzeniu razem", values["post_weaning_deaths"], "szt."),
                cls._card("Stan po odsadzeniu", values["post_weaning_current_stock"], "szt.", tone="is-success"),
            ],
            "section_rows": [],
        }

    @classmethod
    def _feed_section(cls, data):
        efficiency = data["feed_efficiency"]
        production = data["production"]
        return {
            "section_title": "Pasza i śrutowanie",
            "section_description": "Produkcja, koszt FIFO i wskaźniki wykorzystania paszy.",
            "section_cards": [
                cls._card("Wyprodukowana pasza", efficiency["feed_quantity_kg"], "kg"),
                cls._card("Koszt paszy", efficiency["feed_cost"], "zł"),
                cls._card("Średni koszt tony", efficiency["average_feed_cost_per_ton"], "zł/t"),
                cls._card("Pasza / waga żywa", efficiency["feed_to_live_weight_ratio"], "t/t"),
                cls._card("Pasza / waga poubojowa", efficiency["feed_to_slaughter_weight_ratio"], "t/t"),
                cls._card("Zakończone śrutowania", production["completed_count"]),
                cls._card("W kolejce", production["queued_count"]),
                cls._card("W toku", production["in_progress_count"]),
                cls._card("Podana gotowa pasza", data["feed"]["served_quantity_kg"], "kg"),
                cls._card("Stan gotowej paszy", data["feed"]["finished_feed_stock_kg"], "kg"),
                cls._card("Udział paszy w sprzedaży", efficiency["feed_cost_share_of_net_sales_percent"], "%"),
            ],
            "section_rows": data["recipe_ranking"],
            "row_kind": "recipes",
        }

    @classmethod
    def _inventory_section(cls, data):
        values = data["inventory"]
        return {
            "section_title": "Magazyn",
            "section_description": "Bieżący stan surowców i sygnały niskiego zapasu.",
            "section_cards": [
                cls._card("Stan łącznie", values["total_inventory_kg"], "kg"),
                cls._card("Silosy", values["bin_stock_kg"], "kg"),
                cls._card("Workowane / pozostałe", values["bag_stock_kg"], "kg"),
                cls._card("Poniżej progu", values["low_stock_count"]),
                cls._card("Liczba składników", values["ingredient_count"]),
            ],
            "section_rows": [],
        }

    @classmethod
    def _costs_section(cls, data):
        values = data["costs"]
        return {
            "section_title": "Koszty",
            "section_description": "Koszt paszy i pozostałe koszty gospodarstwa bez podwójnego liczenia.",
            "section_cards": [
                cls._card("Koszty razem", values["total"], "zł"),
                cls._card("Koszt paszy", values["feed_cost"], "zł"),
                cls._card("Pozostałe koszty", values["additional"]["total"], "zł"),
                cls._card("Liczba kosztów dodatkowych", values["additional"]["count"]),
                cls._card("Zapłacone", values["paid"], "zł"),
                cls._card("Niezapłacone", values["unpaid"], "zł"),
            ],
            "section_rows": data["timeline"],
            "row_kind": "timeline",
        }

    @staticmethod
    def _timeline(*, sales_monthly, additional_cost_monthly, feed) -> list[dict]:
        rows = defaultdict(lambda: {
            "sales_net": ZERO,
            "sales_gross": ZERO,
            "feed_cost": ZERO,
            "additional_cost": ZERO,
            "production_kg": ZERO,
        })
        for month, values in sales_monthly.items():
            rows[month].update(values)
        for month, values in feed["monthly"].items():
            rows[month].update(values)
        for month, amount in additional_cost_monthly.items():
            rows[month]["additional_cost"] += amount
        for values in rows.values():
            values["result_net"] = values["sales_net"] - values["feed_cost"] - values["additional_cost"]
            values["result_gross"] = values["sales_gross"] - values["feed_cost"] - values["additional_cost"]
        return [{"month": month, **values} for month, values in sorted(rows.items())]

    @staticmethod
    def _profitability(sales_summary, cost_summary, additional_cost_summary, feed, timeline) -> dict:
        total_cost = cost_summary["total"]
        net_sales = sales_summary["net_sales"]
        gross_sales = sales_summary["gross_sales"]
        live_weight = sales_summary["live_weight_kg"]
        return {
            "gross_sales": gross_sales,
            "net_sales": net_sales,
            "vat_sales": sales_summary["vat_sales"],
            "feed_cost": feed["total_cost"],
            "additional_cost": additional_cost_summary["total"],
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
                "title": "Śmiertelność procentowa",
                "reason": "Zgłoszenia upadków są widoczne w sekcji stada; do wskaźnika procentowego nadal potrzebna jest obsada grup tuczowych.",
            },
        ])
        if not feed["quantity_kg"]:
            items.insert(0, {
                "title": "Koszt paszy i FCR",
                "reason": "Brakuje zakończonych śrutowań w wybranym okresie.",
            })
        return items

    @staticmethod
    def statistic_links(active_section="overview") -> list[dict]:
        return [
            {"label": "Podsumowanie", "url": reverse("farm_statistics"), "is_active": active_section == "overview"},
            *[
                {"label": label, "url": reverse("farm_statistics_section", args=[key]), "is_active": active_section == key}
                for key, label in (
                    ("profitability", "Opłacalność"), ("sales", "Sprzedaż"),
                    ("mortality", "Upadki"), ("feed", "Pasza i śrutowanie"),
                    ("inventory", "Magazyn"), ("costs", "Koszty"),
                )
            ],
        ]
