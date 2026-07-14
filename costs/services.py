from decimal import Decimal

from collections import defaultdict

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


class CostReportingService:
    """Publiczny kontrakt odczytowy rejestru kosztów."""

    def __init__(self, farm):
        self.farm = farm

    def summary(self, *, date_from=None, date_to=None) -> dict:
        costs = CostService(self.farm).get_costs(date_from=date_from, date_to=date_to)
        manual_costs = costs.filter(production__isnull=True)
        feed_costs = costs.filter(production__isnull=False)
        result = CostService.summarize(costs)
        result.update({
            "feed_cost": feed_costs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
            "other_cost": manual_costs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
            "additional": CostService.summarize(manual_costs),
            "monthly": self._monthly(costs),
            "additional_monthly": self._monthly(manual_costs),
            "suppliers": list(
                costs.exclude(supplier="")
                .values("supplier")
                .annotate(total=Sum("amount"), count=Count("id"))
                .order_by("-total", "supplier")
            ),
        })
        return result

    @staticmethod
    def _monthly(queryset) -> dict[str, Decimal]:
        rows = defaultdict(lambda: Decimal("0.00"))
        for cost_date, amount in queryset.values_list("date", "amount"):
            rows[cost_date.strftime("%Y-%m")] += amount or Decimal("0.00")
        return dict(rows)
