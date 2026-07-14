from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.core.cache import cache
from django.test import override_settings

from farms.calculators.statistics import (
    FeedEfficiencyCalculator,
    ProfitabilityCalculator,
    StatisticsTimelineCalculator,
)
from farms.services.statistics import FarmStatisticsService
from farms.services.statistics_period import StatisticsPeriod


ZERO = Decimal("0.00")
LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "statistics-architecture-tests",
    },
}


def _sales_report():
    return {
        "sale_count": 1,
        "sold_quantity": 10,
        "slaughter_weight_kg": Decimal("900"),
        "live_weight_kg": Decimal("1200"),
        "net_sales": Decimal("8000"),
        "gross_sales": Decimal("8640"),
        "vat_sales": Decimal("640"),
        "average_price_per_kg": Decimal("8.888"),
        "average_slaughter_weight_per_pig": Decimal("90"),
        "average_live_weight_per_pig": Decimal("120"),
        "average_meatiness": Decimal("58"),
        "average_dressing_percentage": Decimal("75"),
        "unsettled_count": 0,
        "class_distribution": [],
        "monthly": {"2026-01": {"sales_net": Decimal("8000"), "sales_gross": Decimal("8640")}},
    }


def _feed_report():
    return {
        "quantity_kg": Decimal("1000"),
        "total_cost": Decimal("1500"),
        "average_cost_per_kg": Decimal("1.5"),
        "average_cost_per_ton": Decimal("1500"),
        "monthly": {"2026-01": {"production_kg": Decimal("1000"), "feed_cost": Decimal("1500")}},
        "production": {},
        "recipe_ranking": [],
        "details": [],
    }


def _cost_report():
    additional = {"total": Decimal("500"), "count": 1, "categories": []}
    return {
        "total": Decimal("2000"),
        "feed_cost": Decimal("1500"),
        "additional": additional,
        "categories": [],
        "additional_monthly": {"2026-01": Decimal("500")},
    }


def _provider(result):
    provider = Mock()
    provider.summary.return_value = result
    return provider


def test_statistics_period_rejects_reversed_dates():
    with pytest.raises(ValueError):
        StatisticsPeriod(date_from=date(2026, 2, 1), date_to=date(2026, 1, 1))


def test_cross_domain_calculators_keep_one_source_of_truth():
    sales = _sales_report()
    feed = _feed_report()
    costs = _cost_report()
    timeline = StatisticsTimelineCalculator.calculate(
        sales_monthly=sales["monthly"],
        additional_cost_monthly=costs["additional_monthly"],
        feed_monthly=feed["monthly"],
    )
    profitability = ProfitabilityCalculator.calculate(
        sales=sales,
        costs=costs,
        feed=feed,
        timeline=timeline,
    )
    efficiency = FeedEfficiencyCalculator.calculate(
        sales=sales,
        feed=feed,
        profitability=profitability,
    )

    assert profitability["net_result"] == Decimal("6000")
    assert timeline[0]["result_net"] == Decimal("6000")
    assert efficiency["feed_to_live_weight_ratio"] == Decimal("1000") / Decimal("1200")
    assert efficiency["feed_cost_share_of_net_sales_percent"] == Decimal("18.7500")


def test_feed_efficiency_returns_missing_value_instead_of_false_zero():
    sales = {**_sales_report(), "live_weight_kg": ZERO, "slaughter_weight_kg": ZERO, "net_sales": ZERO}
    result = FeedEfficiencyCalculator.calculate(sales=sales, feed=_feed_report())

    assert result["feed_to_live_weight_ratio"] is None
    assert result["feed_to_slaughter_weight_ratio"] is None
    assert result["feed_cost_share_of_net_sales_percent"] is None


def test_sales_section_loads_only_sales_provider():
    sales = _provider(_sales_report())
    unused = {key: _provider({}) for key in ("costs", "feed", "inventory", "mortality", "sows")}
    service = FarmStatisticsService(SimpleNamespace(pk=None), providers={"sales": sales, **unused})

    result = service.section_context("sales", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))

    assert result["active_section"] == "sales"
    assert result["sales"]["sold_quantity"] == 10
    sales.summary.assert_called_once_with(date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
    for provider in unused.values():
        provider.summary.assert_not_called()


def test_profitability_section_loads_only_required_domain_reports():
    providers = {
        "sales": _provider(_sales_report()),
        "costs": _provider(_cost_report()),
        "feed": _provider(_feed_report()),
        "inventory": _provider({}),
        "mortality": _provider({}),
        "sows": _provider({}),
    }
    result = FarmStatisticsService(SimpleNamespace(pk=None), providers=providers).section_context("profitability")

    assert result["profitability"]["net_result"] == Decimal("6000")
    assert result["section_rows"][0]["result_net"] == Decimal("6000")
    for key in ("sales", "costs", "feed"):
        providers[key].summary.assert_called_once()
    for key in ("inventory", "mortality", "sows"):
        providers[key].summary.assert_not_called()


@override_settings(CACHES=LOC_MEM_CACHE)
def test_statistics_section_reuses_cache_for_farm_period_and_section():
    cache.clear()
    sales = _provider(_sales_report())
    service = FarmStatisticsService(SimpleNamespace(pk=987654), providers={"sales": sales})

    first = service.section_context("sales", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))
    second = service.section_context("sales", date_from=date(2026, 1, 1), date_to=date(2026, 12, 31))

    assert first == second
    assert sales.summary.call_count == 1
