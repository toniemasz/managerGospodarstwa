from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum

from sales.models import PigSaleModel


ZERO = Decimal("0.00")


def _safe_divide(numerator, denominator):
    if not denominator:
        return None
    return (numerator or ZERO) / denominator


class SalesReportingService:
    def __init__(self, farm):
        self.farm = farm

    def summary(self, *, date_from=None, date_to=None) -> dict:
        sales = PigSaleModel.objects.filter(farm=self.farm)
        if date_from:
            sales = sales.filter(sale_date__gte=date_from)
        if date_to:
            sales = sales.filter(sale_date__lte=date_to)
        totals = sales.aggregate(
            sale_count=Count("id"), gross=Sum("gross_value"), net=Sum("net_value"),
            quantity=Sum("quantity"), slaughter_weight=Sum("total_weight"),
            live_weight=Sum("live_weight"), vat=Sum("vat_value"),
            avg_meatiness=Avg("avg_meatiness_seurop"),
            avg_dressing=Avg("dressing_percentage"),
            unsettled_count=Count("id", filter=Q(no_settlement=True)),
        )
        sold_quantity = totals["quantity"] or 0
        slaughter_weight = totals["slaughter_weight"] or ZERO
        live_weight = totals["live_weight"] or ZERO
        net = totals["net"] or ZERO
        gross = totals["gross"] or ZERO
        monthly = defaultdict(lambda: {"sales_net": ZERO, "sales_gross": ZERO})
        for sale in sales.only("sale_date", "net_value", "gross_value"):
            if sale.sale_date:
                row = monthly[sale.sale_date.strftime("%Y-%m")]
                row["sales_net"] += sale.net_value or ZERO
                row["sales_gross"] += sale.gross_value or ZERO
        class_distribution = list(
            sales.values("meat_class")
            .annotate(quantity=Sum("quantity"), weight_kg=Sum("total_weight"), net_sales=Sum("net_value"))
            .order_by("meat_class")
        )
        return {
            "sale_count": totals["sale_count"] or 0,
            "sold_quantity": sold_quantity,
            "slaughter_weight_kg": slaughter_weight,
            "live_weight_kg": live_weight,
            "net_sales": net,
            "gross_sales": gross,
            "vat_sales": totals["vat"] or ZERO,
            "average_price_per_kg": _safe_divide(net, slaughter_weight) or ZERO,
            "average_gross_per_live_kg": _safe_divide(gross, live_weight),
            "average_slaughter_weight_per_pig": _safe_divide(slaughter_weight, sold_quantity) or ZERO,
            "average_live_weight_per_pig": _safe_divide(live_weight, sold_quantity),
            "average_meatiness": totals["avg_meatiness"],
            "average_dressing_percentage": totals["avg_dressing"],
            "unsettled_count": totals["unsettled_count"] or 0,
            "class_distribution": class_distribution,
            "monthly": dict(monthly),
        }
