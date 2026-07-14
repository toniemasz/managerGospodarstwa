from django.urls import reverse

from farms.statistics_registry import STATISTICS_SECTION_DEFINITIONS, STATISTICS_SECTIONS


class StatisticsPresenter:
    """Buduje kontrakt UI, nie wykonując zapytań ani obliczeń domenowych."""

    @staticmethod
    def card(title, value, unit="", note="", tone=""):
        return {"title": title, "value": value, "unit": unit, "note": note, "tone": tone}

    @classmethod
    def overview(cls, data: dict) -> dict:
        sales = data["sales"]
        profitability = data["profitability"]
        efficiency = data["feed_efficiency"]
        net_result = profitability["net_result"]
        return {
            "summary_cards": [
                cls.card(
                    "Wynik netto", net_result, "zł",
                    "Sprzedaż minus pasza i koszty",
                    "is-danger" if net_result < 0 else "is-success",
                ),
                cls.card("Sprzedaż netto", sales["net_sales"], "zł", f"{sales['sale_count']} dokumentów"),
                cls.card("Koszt paszy", efficiency["feed_cost"], "zł", "Zakończone śrutowania FIFO"),
                cls.card("Pasza / waga żywa", efficiency["feed_to_live_weight_ratio"], "t/t", "Przybliżony wskaźnik closeout"),
            ],
            "chart_labels": [row["month"] for row in data["timeline"]],
            "chart_datasets": cls.chart_datasets(data["timeline"]),
            "unavailable_indicators": cls.unavailable_indicators(sales, data["feed"]),
        }

    @classmethod
    def section(cls, section: str, data: dict) -> dict:
        if section not in STATISTICS_SECTIONS:
            raise ValueError("Nieznana sekcja statystyk.")
        builder = getattr(cls, f"_{section}_section")
        definition = STATISTICS_SECTIONS[section]
        return {
            "section_title": definition.title,
            "section_description": definition.description,
            "active_section": section,
            **builder(data),
        }

    @classmethod
    def _profitability_section(cls, data):
        values = data["profitability"]
        return {
            "section_cards": [
                cls.card("Wynik netto", values["net_result"], "zł", tone="is-success" if values["net_result"] >= 0 else "is-danger"),
                cls.card("Sprzedaż netto", values["net_sales"], "zł"),
                cls.card("Koszty razem", values["total_cost"], "zł"),
                cls.card("Koszt/kg żywej", values["total_cost_per_live_kg"], "zł/kg"),
                cls.card("Sprzedaż brutto/kg żywej", values["gross_per_live_kg"], "zł/kg"),
                cls.card("Koszt paszy", values["feed_cost"], "zł"),
                cls.card("Pozostałe koszty", values["additional_cost"], "zł"),
                cls.card("Wynik brutto", values["gross_result"], "zł"),
            ],
            "section_rows": data["timeline"],
            "row_kind": "timeline",
        }

    @classmethod
    def _sales_section(cls, data):
        values = data["sales"]
        return {
            "section_cards": [
                cls.card("Sprzedane sztuki", values["sold_quantity"], "szt."),
                cls.card("Dokumenty", values["sale_count"]),
                cls.card("Sprzedaż netto", values["net_sales"], "zł"),
                cls.card("Sprzedaż brutto", values["gross_sales"], "zł"),
                cls.card("VAT", values["vat_sales"], "zł"),
                cls.card("Waga żywa", values["live_weight_kg"], "kg"),
                cls.card("Waga poubojowa", values["slaughter_weight_kg"], "kg"),
                cls.card("Średnia cena/kg", values["average_price_per_kg"], "zł/kg"),
                cls.card("Średnia waga poubojowa/szt.", values["average_slaughter_weight_per_pig"], "kg"),
                cls.card("Średnia waga żywa/szt.", values["average_live_weight_per_pig"], "kg"),
                cls.card("Średnia mięsność", values["average_meatiness"], "%"),
                cls.card("Średni wybój", values["average_dressing_percentage"], "%"),
                cls.card("Nierozliczone dokumenty", values["unsettled_count"]),
            ],
            "section_rows": [
                {"month": month, **row}
                for month, row in sorted(values["monthly"].items())
            ],
            "row_kind": "sales",
        }

    @classmethod
    def _sows_section(cls, data):
        values = data["sows"]
        return {
            "section_cards": [
                cls.card("Aktywne maciory", values["active_sows"], "szt."),
                cls.card("Zarchiwizowane maciory", values["archived_sows"], "szt."),
                cls.card("Inseminacje", values["inseminations"]),
                cls.card("Oproszenia", values["farrowings"]),
                cls.card("Urodzone żywe", values["born_alive"], "szt."),
                cls.card("Urodzone martwe", values["born_dead"], "szt."),
                cls.card("Średnio żywych/miot", values["average_born_alive_per_litter"], "szt."),
                cls.card("Odsadzone", values["weaned"], "szt."),
                cls.card("Średnio odsadzonych/miot", values["average_weaned_per_litter"], "szt."),
                cls.card("Poronienia", values["miscarriages"]),
                cls.card("Dodatnie badania ciąży", values["positive_pregnancy_checks"]),
                cls.card("Skuteczność badań ciąży", values["positive_pregnancy_check_percent"], "%"),
            ],
            "section_rows": values["monthly"],
            "row_kind": "sows",
        }

    @classmethod
    def _mortality_section(cls, data):
        values = data["mortality"]
        return {
            "section_cards": [
                cls.card("Maciory", values["sow_deaths"], "szt."),
                cls.card("Przed odsadzeniem", values["pre_weaning_deaths"], "szt."),
                cls.card("Prosiaki", values["piglet_deaths"], "szt."),
                cls.card("Warchlaki", values["weaner_deaths"], "szt."),
                cls.card("Tuczniki", values["finisher_deaths"], "szt."),
                cls.card("Nieokreślone", values["unspecified_post_weaning_deaths"], "szt."),
                cls.card("Po odsadzeniu razem", values["post_weaning_deaths"], "szt."),
                cls.card("Stan po odsadzeniu", values["current_snapshot"]["post_weaning_current_stock"], "szt.", tone="is-success"),
            ],
            "section_rows": values["by_reason"],
            "row_kind": "mortality",
        }

    @classmethod
    def _feed_section(cls, data):
        efficiency = data["feed_efficiency"]
        feed = data["feed"]
        production = feed["production"]
        return {
            "section_cards": [
                cls.card("Wyprodukowana pasza", efficiency["feed_quantity_kg"], "kg"),
                cls.card("Koszt paszy", efficiency["feed_cost"], "zł"),
                cls.card("Średni koszt tony", efficiency["average_feed_cost_per_ton"], "zł/t"),
                cls.card("Pasza / waga żywa", efficiency["feed_to_live_weight_ratio"], "t/t"),
                cls.card("Pasza / waga poubojowa", efficiency["feed_to_slaughter_weight_ratio"], "t/t"),
                cls.card("Zakończone śrutowania", production["completed_count"]),
                cls.card("W kolejce", production["queued_count"]),
                cls.card("W toku", production["in_progress_count"]),
                cls.card("Podana gotowa pasza", feed["served_quantity_kg"], "kg"),
                cls.card("Stan gotowej paszy", feed["finished_feed_stock_kg"], "kg"),
                cls.card("Udział paszy w sprzedaży", efficiency["feed_cost_share_of_net_sales_percent"], "%"),
                cls.card("Niepełne koszty", feed["partial_cost_count"]),
            ],
            "section_rows": feed["recipe_ranking"],
            "row_kind": "recipes",
        }

    @classmethod
    def _inventory_section(cls, data):
        values = data["inventory"]
        return {
            "section_cards": [
                cls.card("Stan łącznie", values["total_inventory_kg"], "kg"),
                cls.card("Silosy", values["bin_stock_kg"], "kg"),
                cls.card("Workowane / pozostałe", values["bag_stock_kg"], "kg"),
                cls.card("Poniżej progu", values["low_stock_count"]),
                cls.card("Liczba składników", values["ingredient_count"]),
            ],
            "section_rows": values["inventory"],
            "row_kind": "inventory",
        }

    @classmethod
    def _costs_section(cls, data):
        values = data["costs"]
        return {
            "section_cards": [
                cls.card("Koszty razem", values["total"], "zł"),
                cls.card("Koszt paszy", values["feed_cost"], "zł"),
                cls.card("Pozostałe koszty", values["additional"]["total"], "zł"),
                cls.card("Liczba kosztów dodatkowych", values["additional"]["count"]),
                cls.card("Zapłacone", values["paid"], "zł"),
                cls.card("Niezapłacone", values["unpaid"], "zł"),
            ],
            "section_rows": values["categories"],
            "row_kind": "costs",
        }

    @staticmethod
    def chart_datasets(timeline) -> list[dict]:
        return [
            {"label": "Sprzedaż netto", "data": [float(row["sales_net"]) for row in timeline], "borderColor": "#2364aa", "backgroundColor": "rgba(35, 100, 170, .10)"},
            {"label": "Koszty łącznie", "data": [float(row["feed_cost"] + row["additional_cost"]) for row in timeline], "borderColor": "#c92a2a", "backgroundColor": "rgba(201, 42, 42, .08)"},
            {"label": "Wynik netto", "data": [float(row["result_net"]) for row in timeline], "borderColor": "#087f5b", "backgroundColor": "rgba(8, 127, 91, .08)"},
        ]

    @staticmethod
    def unavailable_indicators(sales, feed) -> list[dict]:
        items = []
        if sales["live_weight_kg"] == 0:
            items.append({"title": "Pasza / waga żywa", "reason": "Brakuje wagi żywej w dokumentach sprzedaży."})
        items.extend([
            {"title": "FCR przyrostowy", "reason": "Do dokładnego FCR potrzebna jest masa wejściowa lub przyrost grupy, nie tylko masa sprzedaży."},
            {"title": "ADG i ADFI", "reason": "Średni dzienny przyrost i pobranie paszy wymagają dat wejścia/wyjścia grup oraz liczby dni tuczu."},
            {"title": "Śmiertelność procentowa po odsadzeniu", "reason": "Do wiarygodnego wskaźnika potrzebna jest obsada początkowa grup tuczowych."},
        ])
        if not feed["quantity_kg"]:
            items.insert(0, {"title": "Koszt paszy i FCR", "reason": "Brakuje zakończonych śrutowań w wybranym okresie."})
        return items

    @staticmethod
    def statistic_links(active_section="overview") -> list[dict]:
        return [
            {"label": "Podsumowanie", "url": reverse("farm_statistics"), "is_active": active_section == "overview"},
            *[
                {
                    "label": definition.label,
                    "url": reverse("farm_statistics_section", args=[definition.key]),
                    "is_active": active_section == definition.key,
                }
                for definition in STATISTICS_SECTION_DEFINITIONS
            ],
        ]
