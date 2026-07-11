from decimal import Decimal

from django.db.models import Count, Q, Sum

from costs.models import CostCategoryModel, CostModel


class CostService:
    def __init__(self, farm):
        self.farm = farm

    def get_costs(self, *, year=None, date_from=None, date_to=None, category=None, payment_status=""):
        queryset = CostModel.objects.filter(farm=self.farm).select_related("category", "created_by", "production")
        if year:
            queryset = queryset.filter(date__year=year)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if category:
            queryset = queryset.filter(category=category)
        if payment_status == "paid":
            queryset = queryset.filter(is_paid=True)
        elif payment_status == "unpaid":
            queryset = queryset.filter(is_paid=False)
        return queryset

    @staticmethod
    def summarize(queryset) -> dict:
        totals = queryset.aggregate(
            total=Sum("amount"),
            paid=Sum("amount", filter=Q(is_paid=True)),
            unpaid=Sum("amount", filter=Q(is_paid=False)),
            count=Count("id"),
        )
        category_rows = list(
            queryset.values("category_id", "category__name")
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total", "category__name")
        )
        return {
            "total": totals["total"] or Decimal("0.00"),
            "paid": totals["paid"] or Decimal("0.00"),
            "unpaid": totals["unpaid"] or Decimal("0.00"),
            "count": totals["count"] or 0,
            "largest_category": category_rows[0] if category_rows else None,
            "categories": category_rows,
        }

    def categories(self, *, include_inactive=True):
        queryset = CostCategoryModel.objects.filter(farm=self.farm)
        if not include_inactive:
            queryset = queryset.filter(is_active=True)
        return queryset.order_by("name")
