from django.db.models import Count, Sum

from sows.models import MortalityReportModel
from sows.selectors.mortality import mortality_summary, post_weaning_stock_summary


class MortalityReportingService:
    def __init__(self, farm):
        self.farm = farm

    def summary(self, *, date_from=None, date_to=None) -> dict:
        reports = MortalityReportModel.objects.filter(farm=self.farm)
        if date_from:
            reports = reports.filter(mortality_date__gte=date_from)
        if date_to:
            reports = reports.filter(mortality_date__lte=date_to)
        rows = {
            row["mortality_type"]: row
            for row in reports.values("mortality_type").annotate(report_count=Count("id"), quantity=Sum("quantity"))
        }
        quantity = lambda kind: rows.get(kind, {}).get("quantity") or 0
        stock = post_weaning_stock_summary(self.farm)
        totals = mortality_summary(self.farm, date_from=date_from, date_to=date_to)
        return {
            "sow_deaths": quantity(MortalityReportModel.TYPE_SOW),
            "pre_weaning_deaths": totals["pre_weaning"],
            "piglet_deaths": quantity(MortalityReportModel.TYPE_PIGLET),
            "weaner_deaths": quantity(MortalityReportModel.TYPE_WEANER),
            "finisher_deaths": quantity(MortalityReportModel.TYPE_FINISHER),
            "unspecified_post_weaning_deaths": quantity(MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING),
            "post_weaning_deaths": sum(quantity(kind) for kind in MortalityReportModel.POST_WEANING_TYPES),
            "post_weaning_current_stock": stock["current_stock"],
            "post_weaning_weaned_total": stock["weaned_total"],
            "post_weaning_deaths_total": stock["mortality_total"],
        }
