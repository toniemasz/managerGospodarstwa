from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.urls import reverse
from django.utils import timezone

from costs.models import CostModel
from farms.dashboard_registry import DASHBOARD_STAT_DEFINITIONS, normalize_dashboard_stats
from farms.models import AuditLogModel
from farms.module_registry import MODULE_DEFINITIONS
from farms.services.module_navigation import ModuleNavigationService, normalize_visible_modules
from farms.services.profitability import ProfitabilityAnalyticsService
from farms.services.settings_service import get_farm_settings
from farms.services.task_center import TaskCenterService
from feed.models import ProductionModel
from feed.selectors.inventory import inventory_dashboard
from sales.models import PigSaleModel
from sows.services.sow_dashboard_service import SowDashboardService


class FarmDashboardService:
    def __init__(self, farm):
        self.farm = farm
        self.settings = get_farm_settings(farm)
        self.visible_keys = set(normalize_visible_modules(self.settings.visible_modules))
        self._sow_summary = None
        self._inventory = None
        self._tasks = None
        self._profitability = None

    def get_context(self) -> dict:
        navigation = ModuleNavigationService(self.farm)
        modules = navigation.modules()
        return {
            "dashboard_stats": self._selected_stats(),
            "dashboard_actions": self._quick_actions(),
            "dashboard_modules": navigation.primary_modules(modules) or modules[:4],
            "dashboard_activity": self._activity_items(),
            "dashboard_alerts": self._alert_items(),
        }

    def _selected_stats(self) -> list[dict]:
        selected = normalize_dashboard_stats(
            self.settings.dashboard_stats,
            visible_keys=self.settings.visible_modules,
        )
        definitions = {
            item["key"]: item
            for item in DASHBOARD_STAT_DEFINITIONS
            if item["key"] in selected and item["module"] in self.visible_keys
        }
        cards = []
        for key in selected:
            definition = definitions.get(key)
            calculator = getattr(self, f"_stat_{key}", None)
            if definition and calculator:
                cards.append({**definition, **calculator()})
        return cards

    def _quick_actions(self) -> list[dict]:
        actions = (
            {"module": "sows", "title": "Dodaj zdarzenie", "description": "Szybki zapis zdarzenia maciory.", "url": reverse("bulk_sow_events") + "?rows=1", "icon_name": "sow", "tone": "green"},
            {"module": "sows", "title": "Nowa maciora", "description": "Dodaj kartę zwierzęcia do stada.", "url": reverse("add_sow"), "icon_name": "sow", "tone": "green"},
            {"module": "production", "title": "Zleć śrutowanie", "description": "Dodaj produkcję paszy do kolejki.", "url": reverse("add_production"), "icon_name": "production", "tone": "amber"},
            {"module": "inventory", "title": "Dodaj dostawę", "description": "Przyjmij surowiec na magazyn.", "url": reverse("add_delivery"), "icon_name": "warehouse", "tone": "amber"},
            {"module": "sales", "title": "Nowa sprzedaż", "description": "Zapisz dokument sprzedaży.", "url": reverse("add_sale"), "icon_name": "sales", "tone": "green"},
            {"module": "costs", "title": "Dodaj koszt", "description": "Wprowadź fakturę lub wydatek.", "url": reverse("add_cost"), "icon_name": "costs", "tone": "green"},
        )
        return [action for action in actions if action["module"] in self.visible_keys][:4]

    def _activity_items(self) -> list[dict]:
        logs = AuditLogModel.objects.filter(farm=self.farm).select_related("user")[:4]
        items = []
        for log in logs:
            items.append({
                "title": log.object_repr or log.model_label,
                "description": log.get_action_display() if hasattr(log, "get_action_display") else log.action,
                "time_label": timezone.localtime(log.created_at).strftime("%d.%m, %H:%M"),
                "icon_name": "history",
            })
        return items

    def _alert_items(self) -> list[dict]:
        priority_order = {"urgent": 0, "today": 1, "upcoming": 2}
        items = [
            item
            for tab in self._task_summary()["tab_list"]
            for section in tab["sections"]
            for item in section["items"]
        ]
        items.sort(key=lambda item: (priority_order.get(item["priority"], 9), item.get("due_date") or timezone.localdate()))
        return items[:3]

    def _sows(self) -> dict:
        if self._sow_summary is None:
            self._sow_summary = SowDashboardService(farm=self.farm).get_dashboard_summary()
        return self._sow_summary

    def _inventory_summary(self) -> dict:
        if self._inventory is None:
            self._inventory = inventory_dashboard(self.farm)
        return self._inventory

    def _task_summary(self) -> dict:
        if self._tasks is None:
            self._tasks = TaskCenterService(self.farm).get_tasks()
        return self._tasks

    def _profitability_summary(self) -> dict:
        if self._profitability is None:
            self._profitability = ProfitabilityAnalyticsService(self.farm).calculate()
        return self._profitability

    @staticmethod
    def _count(value) -> str:
        return f"{int(value or 0)}"

    @staticmethod
    def _money(value) -> str:
        amount = Decimal(value or 0).quantize(Decimal("0.01"))
        return f"{amount:,.2f}".replace(",", " ") + " PLN"

    @staticmethod
    def _tonnes(value) -> str:
        amount = Decimal(value or 0).quantize(Decimal("0.01"))
        return f"{amount:,.2f}".replace(",", " ") + " t"

    def _stat_tasks_total(self) -> dict:
        tasks = self._task_summary()
        count = tasks["task_count"]
        return {
            "value": self._count(count),
            "unit": "zadań",
            "note": "Wymagają uwagi" if count else "Brak pilnych spraw",
            "url": reverse("task_center"),
            "tone": "danger" if count else "green",
        }

    def _stat_total_sows(self) -> dict:
        summary = self._sows()
        return {
            "value": self._count(summary["total_sows"]),
            "unit": "szt.",
            "note": f"{summary['pregnant_count']} w ciąży",
            "url": reverse("dashboard"),
        }

    def _stat_pregnant_sows(self) -> dict:
        summary = self._sows()
        return {
            "value": self._count(summary["pregnant_count"]),
            "unit": "szt.",
            "note": "Aktywne cykle rozrodcze",
            "url": reverse("dashboard"),
        }

    def _stat_farrowing_due(self) -> dict:
        count = self._sows()["farrowing_due_count"]
        return {
            "value": self._count(count),
            "unit": "terminów",
            "note": "W oknie alertu",
            "url": reverse("farrowing_panel"),
            "tone": "warning" if count else "green",
        }

    def _stat_vaccinations_due(self) -> dict:
        count = self._sows()["vaccinations_due_count"]
        return {
            "value": self._count(count),
            "unit": "szczepień",
            "note": "Do potwierdzenia",
            "url": reverse("bulk_vaccinate"),
            "tone": "warning" if count else "green",
        }

    def _stat_low_stock(self) -> dict:
        count = len(self._inventory_summary()["low_stock_alerts"])
        return {
            "value": self._count(count),
            "unit": "składników",
            "note": "Poniżej progu" if count else "Stany bezpieczne",
            "url": reverse("feed_inventory"),
            "tone": "danger" if count else "green",
        }

    def _stat_inventory_total(self) -> dict:
        return {
            "value": self._tonnes(self._inventory_summary()["total_inventory_t"]),
            "unit": "",
            "note": "Łączny stan magazynu",
            "url": reverse("feed_full_inventory"),
        }

    def _stat_queued_productions(self) -> dict:
        count = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.QUEUED,
        ).count()
        return {
            "value": self._count(count),
            "unit": "zleceń",
            "note": "W kolejce pasz",
            "url": reverse("feed_productions"),
        }

    def _stat_pending_sales(self) -> dict:
        summary = PigSaleModel.objects.filter(farm=self.farm, no_settlement=True).aggregate(
            count=Count("id"),
            gross=Sum("gross_value"),
        )
        count = summary["count"] or 0
        return {
            "value": self._money(summary["gross"]),
            "unit": "",
            "note": f"{count} bez rozliczenia",
            "url": reverse("sales_list"),
            "tone": "warning" if count else "green",
        }

    def _stat_unpaid_costs(self) -> dict:
        summary = CostModel.objects.filter(farm=self.farm, is_paid=False).aggregate(
            count=Count("id"),
            total=Sum("amount"),
        )
        count = summary["count"] or 0
        return {
            "value": self._money(summary["total"]),
            "unit": "",
            "note": f"{count} nieopłaconych",
            "url": reverse("cost_list"),
            "tone": "warning" if count else "green",
        }

    def _stat_net_result(self) -> dict:
        value = self._profitability_summary()["net_result"]
        return {
            "value": self._money(value),
            "unit": "",
            "note": "Sprzedaż minus koszty",
            "url": reverse("profitability"),
            "tone": "danger" if value < 0 else "green",
        }


def dashboard_stat_groups(form) -> list[dict]:
    module_titles = {module["key"]: module["title"] for module in MODULE_DEFINITIONS}
    groups = []
    for module_key in ("tasks", "sows", "inventory", "production", "sales", "costs", "finance"):
        stats = []
        for stat in DASHBOARD_STAT_DEFINITIONS:
            field_name = f"stat_{stat['key']}"
            if stat["module"] == module_key and field_name in form.fields:
                stats.append({
                    "key": stat["key"],
                    "field": form[field_name],
                    "description": stat["description"],
                    "icon_name": stat["icon_name"],
                    "tone": stat["tone"],
                })
        if stats:
            groups.append({"key": module_key, "title": module_titles.get(module_key, module_key), "stats": stats})
    return groups
