from __future__ import annotations

from django.db.models import Sum
from django.urls import reverse

from common.filter_ui import filter_ui_state, parse_filter_date
from sows.models import MortalityReportModel, SowEventModel


def mortality_list_context(farm, params) -> dict:
    mortality_type = params.get("mortality_type") or ""
    date_from = parse_filter_date(params.get("date_from"))
    date_to = parse_filter_date(params.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    reports = MortalityReportModel.objects.filter(farm=farm).select_related("sow", "created_by")
    if mortality_type in {value for value, _label in MortalityReportModel.TYPE_CHOICES}:
        reports = reports.filter(mortality_type=mortality_type)
    if date_from:
        reports = reports.filter(mortality_date__gte=date_from)
    if date_to:
        reports = reports.filter(mortality_date__lte=date_to)

    context = {
        "mortality_reports": reports,
        "mortality_type_choices": MortalityReportModel.TYPE_CHOICES,
        "selected_mortality_type": mortality_type,
        "date_from": date_from,
        "date_to": date_to,
        "post_weaning_stock": post_weaning_stock_summary(farm),
    }
    context.update(filter_ui_state(params, {
        "mortality_type": "Typ",
        "date_from": "Od",
        "date_to": "Do",
    }))
    context["filter_clear_url"] = reverse("mortality_list")
    return context


def post_weaning_stock_summary(farm) -> dict:
    weaned_total = _sum_weaned_animals(farm)
    mortality_total = (
        MortalityReportModel.objects
        .filter(farm=farm, mortality_type=MortalityReportModel.TYPE_POST_WEANING)
        .aggregate(total=Sum("quantity"))
        .get("total") or 0
    )
    current_stock = max(0, weaned_total - mortality_total)
    return {
        "weaned_total": weaned_total,
        "mortality_total": mortality_total,
        "current_stock": current_stock,
    }


def _sum_weaned_animals(farm) -> int:
    total = 0
    for details in SowEventModel.objects.filter(
        sow__farm=farm,
        event_type="WEANING",
    ).values_list("details", flat=True):
        try:
            total += int((details or {}).get("count") or 0)
        except (TypeError, ValueError):
            continue
    return total
