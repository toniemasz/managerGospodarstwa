from decimal import Decimal

from django.db.models import Count, Sum

from sales.models import PigSaleModel


class SalesDashboardProvider:
    def __init__(self, farm):
        self.farm = farm

    def pending_summary(self) -> dict:
        values = PigSaleModel.objects.filter(farm=self.farm, no_settlement=True).aggregate(
            count=Count("id"),
            gross=Sum("gross_value"),
        )
        return {"count": values["count"] or 0, "gross": values["gross"] or Decimal("0.00")}

    def unsettled(self):
        return PigSaleModel.objects.filter(
            farm=self.farm,
            no_settlement=True,
        ).order_by("sale_date", "id")

    def recent(self, *, limit=5):
        return PigSaleModel.objects.filter(farm=self.farm).order_by("-created_at", "-sale_date", "-id")[:limit]

    def net_between(self, date_from, date_to):
        return PigSaleModel.objects.filter(
            farm=self.farm,
            sale_date__gte=date_from,
            sale_date__lte=date_to,
        ).aggregate(total=Sum("net_value"))["total"] or Decimal("0.00")
