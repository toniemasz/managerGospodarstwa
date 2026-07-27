from django.db.models import Sum

from sows.models import MortalityReportModel, SowEventModel
from sows.services.piglet_care import PigletCareService


class SowActivityProvider:
    def __init__(self, farm):
        self.farm = farm

    def recent_events(self, *, limit=5):
        return SowEventModel.objects.filter(
            sow__farm=self.farm,
        ).select_related("sow").order_by("-created_at", "-event_date", "-id")[:limit]

    def recent_mortality(self, *, limit=5, since=None):
        reports = MortalityReportModel.objects.filter(farm=self.farm)
        if since is not None:
            reports = reports.filter(mortality_date__gte=since)
        return reports.select_related("sow").order_by("-created_at", "-mortality_date", "-id")[:limit]

    def mortality_total_between(self, date_from, date_to) -> int:
        manual_total = MortalityReportModel.objects.filter(
            farm=self.farm,
            mortality_date__gte=date_from,
            mortality_date__lte=date_to,
        ).aggregate(total=Sum("quantity"))["total"] or 0
        automatic_total = sum(
            row.automatic_deaths
            for row in PigletCareService(
                self.farm
            ).completed_cycle_reconciliations(weaned_from=date_from)
            if row.mortality_date <= date_to
        )
        return manual_total + automatic_total
