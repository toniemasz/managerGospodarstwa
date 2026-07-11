from decimal import Decimal

from django.db.models import Count, Q, Sum

from costs.models import CostModel


class CostDashboardProvider:
    def __init__(self, farm):
        self.farm = farm

    def unpaid_summary(self) -> dict:
        values = CostModel.objects.filter(farm=self.farm, is_paid=False).aggregate(
            count=Count("id"),
            total=Sum("amount"),
        )
        return {"count": values["count"] or 0, "total": values["total"] or Decimal("0.00")}

    def attention_costs(self):
        return CostModel.objects.filter(farm=self.farm).filter(
            Q(category__isnull=True) | Q(is_paid=False)
        ).select_related("category").order_by("date", "id")

    def recent(self, *, limit=5):
        return CostModel.objects.filter(farm=self.farm).order_by("-created_at", "-date", "-id")[:limit]

    def total_between(self, date_from, date_to):
        return CostModel.objects.filter(
            farm=self.farm,
            date__gte=date_from,
            date__lte=date_to,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
