from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from sows.models import MortalityReportModel, PigletTransferModel, SowEventModel, SowModel
from sows.selectors.mortality import mortality_summary, post_weaning_stock_summary
from sows.services.sow_metrics import METRICS_REGISTRY, MetricDescriptor
from sows.services.sow_repository import SowRepository


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
        by_reason = list(
            reports.values("reason")
            .annotate(report_count=Count("id"), quantity=Sum("quantity"))
            .order_by("-quantity", "reason")
        )
        monthly = defaultdict(int)
        for mortality_date, report_quantity in reports.values_list("mortality_date", "quantity"):
            monthly[mortality_date.strftime("%Y-%m")] += report_quantity or 0
        period = {
            "sow_deaths": quantity(MortalityReportModel.TYPE_SOW),
            "pre_weaning_deaths": totals["pre_weaning"],
            "piglet_deaths": quantity(MortalityReportModel.TYPE_PIGLET),
            "weaner_deaths": quantity(MortalityReportModel.TYPE_WEANER),
            "finisher_deaths": quantity(MortalityReportModel.TYPE_FINISHER),
            "unspecified_post_weaning_deaths": quantity(MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING),
            "post_weaning_deaths": sum(quantity(kind) for kind in MortalityReportModel.POST_WEANING_TYPES),
        }
        current_snapshot = {
            "post_weaning_current_stock": stock["current_stock"],
            "post_weaning_weaned_total": stock["weaned_total"],
            "post_weaning_deaths_total": stock["mortality_total"],
        }
        return {
            **period,
            **current_snapshot,
            "period": period,
            "current_snapshot": current_snapshot,
            "by_reason": by_reason,
            "monthly": [{"month": month, "quantity": value} for month, value in sorted(monthly.items())],
        }


class SowReportingService:
    """Publiczny kontrakt statystyk rozrodu, niezależny od dashboardu i alertów."""

    def __init__(self, farm=None, repository: SowRepository | None = None):
        if farm is None and repository is None:
            raise ValueError("Statystyki macior wymagają jawnego gospodarstwa.")
        self.farm = farm
        self.repository = repository or SowRepository(farm=farm)

    def summary(self, *, date_from=None, date_to=None) -> dict:
        if self.farm is None:
            raise ValueError("Agregacja statystyk macior wymaga gospodarstwa.")
        events = SowEventModel.objects.filter(sow__farm=self.farm)
        if date_from:
            events = events.filter(event_date__gte=date_from)
        if date_to:
            events = events.filter(event_date__lte=date_to)

        totals = defaultdict(int)
        monthly = defaultdict(lambda: defaultdict(int))
        for event_type, event_date, details in events.values_list("event_type", "event_date", "details"):
            details = details or {}
            month = monthly[event_date.strftime("%Y-%m")]
            month["month"] = event_date.strftime("%Y-%m")
            if event_type == "INSEMINATION":
                totals["inseminations"] += 1
                month["inseminations"] += 1
            elif event_type == "PREGNANCY_CHECK":
                totals["pregnancy_checks"] += 1
                month["pregnancy_checks"] += 1
                if str(details.get("result", "")).upper() == "TAK":
                    totals["positive_pregnancy_checks"] += 1
                    month["positive_pregnancy_checks"] += 1
            elif event_type == "FARROWING":
                born_alive = int(details.get("born_alive") or 0)
                born_dead = int(details.get("born_dead") or 0)
                totals["farrowings"] += 1
                totals["born_alive"] += born_alive
                totals["born_dead"] += born_dead
                month["farrowings"] += 1
                month["born_alive"] += born_alive
                month["born_dead"] += born_dead
            elif event_type == "WEANING":
                weaned = int(details.get("count") or 0)
                totals["weanings"] += 1
                totals["weaned"] += weaned
                month["weanings"] += 1
                month["weaned"] += weaned
            elif event_type == "MISCARRIAGE":
                totals["miscarriages"] += 1
                month["miscarriages"] += 1

        transfers = PigletTransferModel.objects.filter(
            farm=self.farm,
            canceled_at__isnull=True,
        )
        if date_from:
            transfers = transfers.filter(transfer_date__gte=date_from)
        if date_to:
            transfers = transfers.filter(transfer_date__lte=date_to)
        for transfer_date, quantity in transfers.values_list("transfer_date", "quantity"):
            month = monthly[transfer_date.strftime("%Y-%m")]
            month["month"] = transfer_date.strftime("%Y-%m")
            totals["piglets_received"] += quantity
            totals["piglets_transferred"] += quantity
            month["piglets_received"] += quantity
            month["piglets_transferred"] += quantity

        active_sows = SowModel.objects.filter(farm=self.farm, is_archived=False).count()
        archived_sows = SowModel.objects.filter(farm=self.farm, is_archived=True).count()
        farrowings = totals["farrowings"]
        weanings = totals["weanings"]
        pregnancy_checks = totals["pregnancy_checks"]
        return {
            "active_sows": active_sows,
            "archived_sows": archived_sows,
            "inseminations": totals["inseminations"],
            "pregnancy_checks": pregnancy_checks,
            "positive_pregnancy_checks": totals["positive_pregnancy_checks"],
            "positive_pregnancy_check_percent": (
                Decimal(totals["positive_pregnancy_checks"]) / Decimal(pregnancy_checks) * Decimal("100")
                if pregnancy_checks else None
            ),
            "farrowings": farrowings,
            "born_alive": totals["born_alive"],
            "born_dead": totals["born_dead"],
            "average_born_alive_per_litter": (
                Decimal(totals["born_alive"]) / Decimal(farrowings) if farrowings else None
            ),
            "weanings": weanings,
            "weaned": totals["weaned"],
            "piglets_received": totals["piglets_received"],
            "piglets_transferred": totals["piglets_transferred"],
            "average_weaned_per_litter": (
                Decimal(totals["weaned"]) / Decimal(weanings) if weanings else None
            ),
            "miscarriages": totals["miscarriages"],
            "monthly": [dict(values) for _month, values in sorted(monthly.items())],
        }

    def metric_ranking(
        self,
        metric_key: str,
        months_limit: int = 6,
        order: str = "desc",
        date_from=None,
        date_to=None,
    ) -> dict:
        """Zwraca trend i ranking metryki, uwzględniając dane historycznych macior."""
        if metric_key not in METRICS_REGISTRY:
            metric_key = next(iter(METRICS_REGISTRY))
        metric: MetricDescriptor = METRICS_REGISTRY[metric_key]
        getter = (
            self.repository.get_sows_for_statistics
            if self.farm is not None
            else self.repository.get_all_sows
        )
        sows = getter()
        cutoff_date, end_date = self._resolve_period(
            months_limit=months_limit,
            date_from=date_from,
            date_to=date_to,
        )
        monthly_data = defaultdict(int)
        ranking = []
        for sow in sows:
            sow_total = 0
            for event in sow.all_events:
                if event.event_type != metric.event_type or not cutoff_date <= event.event_date <= end_date:
                    continue
                value = metric.value_extractor(event.details)
                sow_total += value
                monthly_data[event.event_date.strftime("%Y-%m")] += value
            if sow_total > 0 or sow.status != "ARCHIVED":
                ranking.append({
                    "id": sow.id,
                    "ear_tag": sow.ear_tag,
                    "total_value": sow_total,
                    "status": sow.dynamic_status_display,
                })
        ranking.sort(key=lambda item: item["total_value"], reverse=order != "asc")
        months = sorted(monthly_data)
        return {
            "current_metric": metric,
            "available_metrics": METRICS_REGISTRY.values(),
            "current_months_limit": months_limit,
            "current_order": order,
            "top_sows": ranking[:10],
            "chart_labels": months,
            "chart_values": [monthly_data[month] for month in months],
        }

    @staticmethod
    def _resolve_period(*, months_limit, date_from, date_to):
        if date_from is not None or date_to is not None:
            return date_from or date.min, date_to or date.max
        if months_limit == 0:
            return date.min, date.max
        today = timezone.localdate()
        month_index = today.year * 12 + today.month - 1 - months_limit
        return date(month_index // 12, month_index % 12 + 1, 1), today
