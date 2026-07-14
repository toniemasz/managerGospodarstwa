from __future__ import annotations

from common.cache import STATISTICS_TTL, cached_farm_value
from costs.services import CostReportingService
from farms.calculators.statistics import (
    FeedEfficiencyCalculator,
    ProfitabilityCalculator,
    StatisticsTimelineCalculator,
)
from farms.services.statistics_period import StatisticsPeriod
from farms.services.statistics_presenter import StatisticsPresenter
from farms.statistics_registry import STATISTICS_SECTION_KEYS, STATISTICS_SECTIONS
from feed.services.reporting import FeedReportingService, InventoryReportingService
from sales.services.reporting import SalesReportingService
from sows.services.reporting import MortalityReportingService, SowReportingService


class FarmStatisticsService:
    """Fasada składająca raporty domenowe bez przejmowania ich reguł biznesowych."""

    SECTION_KEYS = STATISTICS_SECTION_KEYS
    OVERVIEW_DEPENDENCIES = ("sales", "costs", "feed", "inventory", "mortality", "sows", "profitability", "feed_efficiency")

    def __init__(self, farm, *, providers=None):
        self.farm = farm
        self.providers = providers or {}

    def calculate(self, *, date_from=None, date_to=None) -> dict:
        """Zachowuje publiczny kontrakt pełnego podsumowania statystyk."""
        period = StatisticsPeriod.from_dates(date_from=date_from, date_to=date_to)
        return cached_farm_value(
            self.farm,
            "statistics",
            ("overview", *period.cache_parts),
            timeout=STATISTICS_TTL,
            builder=lambda: self._overview(period),
        )

    def section_context(self, section, *, date_from=None, date_to=None) -> dict:
        """Ładuje wyłącznie raporty wymagane przez wskazaną sekcję."""
        if section not in STATISTICS_SECTIONS:
            raise ValueError("Nieznana sekcja statystyk.")
        period = StatisticsPeriod.from_dates(date_from=date_from, date_to=date_to)
        return cached_farm_value(
            self.farm,
            "statistics",
            ("section", section, *period.cache_parts),
            timeout=STATISTICS_TTL,
            builder=lambda: self._section(section, period),
        )

    def profitability_context(self, *, date_from=None, date_to=None) -> dict:
        """Zwraca dane strony opłacalności bez ładowania magazynu, stada i upadków."""
        period = StatisticsPeriod.from_dates(date_from=date_from, date_to=date_to)
        return cached_farm_value(
            self.farm,
            "statistics",
            ("profitability", *period.cache_parts),
            timeout=STATISTICS_TTL,
            builder=lambda: self._profitability_page_data(period),
        )

    def _profitability_page_data(self, period: StatisticsPeriod) -> dict:
        data = self._build_data(
            ("sales", "costs", "feed", "profitability", "feed_efficiency"),
            period,
        )
        data.update({
            "additional_costs": data["costs"]["additional"],
            "production_details": data["feed"]["details"],
            "chart_labels": [row["month"] for row in data["timeline"]],
            "chart_datasets": StatisticsPresenter.chart_datasets(data["timeline"]),
        })
        return data

    def _overview(self, period: StatisticsPeriod) -> dict:
        data = self._build_data(self.OVERVIEW_DEPENDENCIES, period)
        data.update({
            "additional_costs": data["costs"]["additional"],
            "production": data["feed"]["production"],
            "recipe_ranking": data["feed"]["recipe_ranking"],
            "production_details": data["feed"]["details"],
        })
        data.update(StatisticsPresenter.overview(data))
        return data

    def _section(self, section: str, period: StatisticsPeriod) -> dict:
        definition = STATISTICS_SECTIONS[section]
        data = self._build_data(definition.dependencies, period)
        data.update(StatisticsPresenter.section(section, data))
        return data

    def _build_data(self, dependencies, period: StatisticsPeriod) -> dict:
        requested = set(dependencies)
        if "profitability" in requested:
            requested.update(("sales", "costs", "feed"))
        if "feed_efficiency" in requested:
            requested.update(("sales", "feed"))

        data = {}
        for dependency in ("sales", "costs", "feed", "inventory", "mortality", "sows"):
            if dependency in requested:
                data[dependency] = self._summary(dependency, period)

        if "profitability" in requested:
            data["timeline"] = StatisticsTimelineCalculator.calculate(
                sales_monthly=data["sales"]["monthly"],
                additional_cost_monthly=data["costs"]["additional_monthly"],
                feed_monthly=data["feed"]["monthly"],
            )
            data["profitability"] = ProfitabilityCalculator.calculate(
                sales=data["sales"],
                costs=data["costs"],
                feed=data["feed"],
                timeline=data["timeline"],
            )
        if "feed_efficiency" in requested:
            data["feed_efficiency"] = FeedEfficiencyCalculator.calculate(
                sales=data["sales"],
                feed=data["feed"],
                profitability=data.get("profitability"),
            )
        return data

    def _summary(self, dependency: str, period: StatisticsPeriod) -> dict:
        provider = self.providers.get(dependency) or self._default_provider(dependency)
        if dependency == "inventory":
            return provider.summary()
        return provider.summary(date_from=period.date_from, date_to=period.date_to)

    def _default_provider(self, dependency: str):
        providers = {
            "sales": SalesReportingService,
            "costs": CostReportingService,
            "feed": FeedReportingService,
            "inventory": InventoryReportingService,
            "mortality": MortalityReportingService,
            "sows": SowReportingService,
        }
        return providers[dependency](self.farm)

    @staticmethod
    def statistic_links(active_section="overview") -> list[dict]:
        return StatisticsPresenter.statistic_links(active_section)
