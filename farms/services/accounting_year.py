from dataclasses import dataclass
from datetime import date

from django.utils import timezone


@dataclass(frozen=True)
class AccountingYear:
    year: int
    date_from: date
    date_to: date


def parse_accounting_year(params, *, default_year=None) -> AccountingYear:
    current = default_year or timezone.localdate().year
    try:
        year = int(params.get("year", current))
    except (TypeError, ValueError):
        year = current
    if year < 2000 or year > 2100:
        year = current
    return AccountingYear(year=year, date_from=date(year, 1, 1), date_to=date(year, 12, 31))


def get_available_years(farm) -> list[int]:
    from costs.models import CostModel
    from feed.models import ProductionModel
    from sales.models import PigSaleModel
    from sows.models import MortalityReportModel, SowEventModel

    years = {timezone.localdate().year}
    years.update(PigSaleModel.objects.filter(farm=farm, sale_date__isnull=False).values_list("sale_date__year", flat=True).distinct())
    years.update(CostModel.objects.filter(farm=farm).values_list("date__year", flat=True).distinct())
    years.update(ProductionModel.objects.filter(recipe__farm=farm).values_list("date__year", flat=True).distinct())
    years.update(SowEventModel.objects.filter(sow__farm=farm).values_list("event_date__year", flat=True).distinct())
    years.update(MortalityReportModel.objects.filter(farm=farm).values_list("mortality_date__year", flat=True).distinct())
    return sorted((year for year in years if year), reverse=True)
