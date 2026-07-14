from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from costs.dashboard import CostDashboardProvider
from common.cache import TODAY_DASHBOARD_TTL, cached_farm_value
from farms.services.module_navigation import ModuleNavigationService, normalize_visible_modules
from farms.services.settings_service import get_farm_settings
from farms.services.task_center import TaskCenterService
from feed.services.dashboard import FeedDashboardProvider
from sales.dashboard import SalesDashboardProvider
from sows.services.activity import SowActivityProvider
from sows.services.sow_dashboard_service import SowDashboardService
from common.units import format_mass


class TodayDashboardService:
    """Agreguje dane do operacyjnego ekranu dziennego bez zapisu danych."""

    TASK_SECTION_MODULES = {
        "ultrasound": "sows",
        "vaccination": "sows",
        "farrowing": "sows",
        "low_stock": "inventory",
        "queued": "production",
        "stage_one": "production",
        "unsettled_sales": "sales",
        "costs": "costs",
    }
    TASK_GROUP_DEFINITIONS = {
        "vaccination": {
            "title": "Szczepienia",
            "description": "Zaplanowane szczepienia do zatwierdzenia.",
            "action_label": "Wypełnij",
            "panel_url_name": "bulk_vaccinate",
            "icon_name": "health",
            "tone": "green",
            "order": 10,
        },
        "ultrasound": {
            "title": "Badania USG",
            "description": "Kontrole prośności do zapisania.",
            "action_label": "Wypełnij wyniki",
            "panel_url_name": "bulk_pregnancy_check",
            "icon_name": "tasks",
            "tone": "warning",
            "order": 20,
        },
        "farrowing": {
            "title": "Oproszenia",
            "description": "Maciory w oknie porodu.",
            "action_label": "Dodaj poród",
            "panel_url_name": "farrowing_panel",
            "icon_name": "calendar",
            "tone": "green",
            "order": 30,
        },
        "low_stock": {
            "title": "Dostawy",
            "description": "Składniki poniżej progu.",
            "action_label": "Dodaj dostawę",
            "panel_url_name": "add_delivery",
            "icon_name": "warehouse",
            "tone": "danger",
            "order": 40,
        },
        "production_stage_2": {
            "title": "Śrutowanie",
            "description": "Produkcje gotowe do etapu 2.",
            "action_label": "Otwórz śrutowanie",
            "panel_url_name": "feed_productions",
            "icon_name": "production",
            "tone": "amber",
            "order": 50,
        },
        "unsettled_sale": {
            "title": "Sprzedaż",
            "description": "Sprzedaże wymagające rozliczenia.",
            "action_label": "Uzupełnij sprzedaż",
            "panel_url_name": "sales_list",
            "icon_name": "sales",
            "tone": "warning",
            "order": 60,
        },
        "cost_attention": {
            "title": "Koszty",
            "description": "Koszty do uzupełnienia albo opłacenia.",
            "action_label": "Uzupełnij koszt",
            "panel_url_name": "cost_list",
            "icon_name": "costs",
            "tone": "warning",
            "order": 70,
        },
    }

    def __init__(self, farm):
        self.farm = farm
        self.today = timezone.localdate()
        self.month_start = self.today.replace(day=1)
        self.settings = get_farm_settings(farm)
        self.visible_keys = set(normalize_visible_modules(self.settings.visible_modules))
        self._tasks = None
        self._sows = None
        self._inventory = None
        self.feed_provider = FeedDashboardProvider(farm)
        self.sales_provider = SalesDashboardProvider(farm)
        self.cost_provider = CostDashboardProvider(farm)
        self.sow_activity_provider = SowActivityProvider(farm)

    def get_context(self) -> dict:
        return cached_farm_value(
            self.farm,
            "today_dashboard",
            (self.today,),
            timeout=TODAY_DASHBOARD_TTL,
            builder=self._build_context,
        )

    def _build_context(self) -> dict:
        tasks = self._visible_tasks()
        alerts = self._alert_items(tasks)
        recent_events = self._recent_events()
        return {
            "today_quick_actions": self._quick_actions(),
            "today_tasks": tasks[:20],
            "today_quick_tasks": tasks[:6],
            "today_task_groups": self._today_task_groups(tasks),
            "today_task_count": len(tasks),
            "today_completable_task_count": len([task for task in tasks if task["can_quick_complete"]]),
            "today_alerts": alerts[:8],
            "today_quick_alerts": alerts[:4],
            "today_urgent_alert_count": len([item for item in alerts if item["priority"] in {"urgent", "today"}]),
            "today_kpis": self._kpi_cards(),
            "today_recent_events": recent_events,
            "today_quick_recent_events": recent_events[:5],
            "today_full_links": self._full_links(),
        }

    def completable_tasks_by_id(self) -> dict[str, dict]:
        return {
            task["task_id"]: task
            for task in self._visible_tasks()
            if task["can_quick_complete"]
        }

    def _quick_actions(self) -> list[dict]:
        actions = [
            ("sows", "Dodaj zdarzenie maciory", "Zapisz inseminację, USG, oproszenie albo odsadzenie.", reverse("bulk_sow_events") + "?rows=1", "sow", "green"),
            ("sows", "Zgłoś upadek", "Zapisz upadek maciory lub zwierząt po odsadzeniu.", reverse("report_mortality"), "warning", "danger"),
            ("sows", "Dodaj poród", "Zapisz oproszenie z wynikiem miotu.", reverse("bulk_sow_events") + "?rows=1&event_type=FARROWING", "calendar", "green"),
            ("sows", "Dodaj odsadzenie", "Zapisz liczbę odsadzonych prosiąt.", reverse("bulk_sow_events") + "?rows=1&event_type=WEANING", "sow", "green"),
            ("sows", "Dodaj szczepienie", "Zapisz szczepienie pojedynczej maciory.", reverse("bulk_sow_events") + "?rows=1&event_type=VACCINATION", "health", "green"),
            ("inventory", "Dodaj dostawę", "Przyjmij składnik paszowy na magazyn.", reverse("add_delivery"), "warehouse", "amber"),
            ("production", "Dodaj śrutowanie", "Zaplanuj produkcję paszy.", reverse("add_production"), "production", "amber"),
            ("sales", "Dodaj sprzedaż", "Zapisz dokument sprzedaży.", reverse("add_sale"), "sales", "green"),
            ("costs", "Dodaj koszt", "Wprowadź fakturę albo wydatek.", reverse("add_cost"), "costs", "green"),
        ]
        return [
            {
                "title": title,
                "description": description,
                "url": url,
                "icon_name": icon_name,
                "tone": tone,
            }
            for module_key, title, description, url, icon_name, tone in actions
            if self._module_visible(module_key)
        ]

    def _visible_tasks(self) -> list[dict]:
        items = []
        for tab in self._task_summary()["tab_list"]:
            for section in tab["sections"]:
                if not self._module_visible(self.TASK_SECTION_MODULES.get(section["key"])):
                    continue
                items.extend(section["items"])
        priority_order = {"urgent": 0, "today": 1, "upcoming": 2}
        sorted_items = sorted(
            items,
            key=lambda item: (
                priority_order.get(item["priority"], 9),
                item.get("due_date") or self.today,
                item["title"],
            ),
        )
        return [self._task_for_today(item) for item in sorted_items]

    def _task_for_today(self, item: dict) -> dict:
        task = {**item, "metadata": {**(item.get("metadata") or {})}}
        task["task_id"] = self._task_id(task)
        kind = task["metadata"].get("kind")
        task["can_quick_complete"] = kind in {"ultrasound", "vaccination"}
        task["quick_complete_kind"] = kind if task["can_quick_complete"] else ""
        if kind == "ultrasound":
            task["quick_complete_label"] = "Zapisze badanie USG z dzisiejszą datą."
        elif kind == "vaccination":
            task["quick_complete_label"] = "Zapisze szczepienie z dzisiejszą datą."
        else:
            task["quick_complete_label"] = "Wymaga uzupełnienia w formularzu."
        return task

    def _today_task_groups(self, tasks: list[dict]) -> list[dict]:
        groups = {}
        for task in tasks:
            if not self._task_belongs_to_today(task):
                continue
            kind = (task.get("metadata") or {}).get("kind") or "other"
            definition = self.TASK_GROUP_DEFINITIONS.get(kind, self._default_task_group_definition(task))
            group = groups.setdefault(kind, self._new_task_group(kind, definition))
            group["tasks"].append(task)
            group["count"] += 1
            if task["priority"] in {"urgent", "today"}:
                group["urgent_count"] += 1
            if task["can_quick_complete"]:
                group["can_quick_complete"] = True
                group["quick_complete_kind"] = task["quick_complete_kind"]

        for group in groups.values():
            group["preview_items"] = group["tasks"][:3]
            group["more_count"] = max(0, group["count"] - len(group["preview_items"]))
            if group["can_quick_complete"]:
                group["action_label"] = group["action_label"] or "Wypełnij"

        return sorted(
            groups.values(),
            key=lambda group: (
                group["order"],
                -group["urgent_count"],
                group["title"],
            ),
        )

    def _task_belongs_to_today(self, task: dict) -> bool:
        due_date = task.get("due_date")
        return (
            task["priority"] in {"urgent", "today"}
            or (due_date is not None and due_date <= self.today)
        )

    def _new_task_group(self, key: str, definition: dict) -> dict:
        panel_url_name = definition.get("panel_url_name")
        return {
            "key": key,
            "title": definition["title"],
            "description": definition["description"],
            "action_label": definition.get("action_label", "Otwórz"),
            "panel_url": reverse(panel_url_name) if panel_url_name else reverse("task_center"),
            "icon_name": definition.get("icon_name", "tasks"),
            "tone": definition.get("tone", "neutral"),
            "order": definition.get("order", 999),
            "dialog_id": f"today-task-dialog-{key}",
            "can_quick_complete": False,
            "quick_complete_kind": "",
            "count": 0,
            "urgent_count": 0,
            "tasks": [],
            "preview_items": [],
            "more_count": 0,
        }

    @staticmethod
    def _default_task_group_definition(task: dict) -> dict:
        return {
            "title": task.get("status_label") or "Zadania",
            "description": "Zadania wymagające obsługi.",
            "action_label": task.get("action_label") or "Otwórz",
            "panel_url_name": None,
            "icon_name": "tasks",
            "tone": "neutral",
            "order": 900,
        }

    def _task_id(self, task: dict) -> str:
        metadata = task.get("metadata") or {}
        raw_parts = [
            metadata.get("kind", "task"),
            metadata.get("sow_id", ""),
            metadata.get("ingredient_id", ""),
            metadata.get("production_id", ""),
            metadata.get("sale_id", ""),
            metadata.get("cost_id", ""),
            metadata.get("vaccine_name", ""),
            metadata.get("cycle_id", ""),
            task.get("due_date") or "",
            task.get("title", ""),
        ]
        raw = "|".join(str(part) for part in raw_parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _alert_items(self, tasks: list[dict]) -> list[dict]:
        alerts = [
            {
                "title": task["title"],
                "description": task["description"],
                "priority": task["priority"],
                "status_label": task["status_label"],
                "url": task["action_url"] or task["object_url"],
            }
            for task in tasks
            if task["priority"] in {"urgent", "today"}
        ]
        if self._module_visible("sows"):
            alerts.extend(self._recent_mortality_alerts())
        return alerts

    def _recent_mortality_alerts(self) -> list[dict]:
        since = self.today - timedelta(days=7)
        reports = self.sow_activity_provider.recent_mortality(limit=3, since=since)
        return [
            {
                "title": report.get_mortality_type_display(),
                "description": self._mortality_description(report),
                "priority": "today" if report.mortality_date == self.today else "upcoming",
                "status_label": report.mortality_date.strftime("%d.%m.%Y"),
                "url": reverse("mortality_list"),
            }
            for report in reports
        ]

    def _kpi_cards(self) -> list[dict]:
        cards = []
        if self._module_visible("sows"):
            summary = self._sow_summary()
            cards.extend([
                self._kpi("Aktywne maciory", summary["total_sows"], "szt.", "Stado bieżące.", "sow", "green", reverse("dashboard")),
                self._kpi("Prośne", summary["pregnant_count"], "szt.", "Potwierdzone ciąże.", "sow", "green", reverse("dashboard")),
                self._kpi("Karmiące", summary["lactating_count"], "szt.", "Maciory po oproszeniu.", "sow", "green", reverse("dashboard")),
                self._kpi("Do kontroli", len(summary["sows_to_check_usg"]), "szt.", "Wymagają USG.", "tasks", "warning", reverse("bulk_pregnancy_check")),
                self._kpi("Do porodu", summary["farrowing_due_count"], "szt.", "W oknie alertu.", "calendar", "warning", reverse("farrowing_panel")),
                self._kpi("Upadki w miesiącu", self._mortality_month_total(), "szt.", "Ręczne i wyliczone przed odsadzeniem.", "warning", "danger", reverse("mortality_list")),
            ])
        if self._module_visible("inventory"):
            cards.append(self._kpi("Niskie stany paszy", len(self._inventory_summary()["low_stock_alerts"]), "skł.", "Poniżej progu.", "warning", "danger", reverse("feed_inventory")))
        if self._module_visible("production"):
            cards.append(self._kpi("Produkcje w toku", self._production_in_progress_count(), "zleceń", "Po etapie 1.", "production", "amber", reverse("feed_productions")))
        if self._module_visible("sales"):
            cards.append(self._kpi("Sprzedaż netto", self._sales_net_this_month(), "zł", "Bieżący miesiąc.", "sales", "green", reverse("sales_list")))
        if self._module_visible("costs"):
            cards.append(self._kpi("Koszty", self._costs_this_month(), "zł", "Bieżący miesiąc.", "costs", "warning", reverse("cost_list")))
        return cards[:10]

    @staticmethod
    def _kpi(title, value, unit, note, icon_name, tone, url) -> dict:
        return {
            "title": title,
            "value": value or 0,
            "unit": unit,
            "note": note,
            "icon_name": icon_name,
            "tone": tone,
            "url": url,
        }

    def _recent_events(self) -> list[dict]:
        items = []
        if self._module_visible("sows"):
            items.extend(self._recent_sow_events())
            items.extend(self._recent_mortality_events())
        if self._module_visible("inventory"):
            items.extend(self._recent_deliveries())
        if self._module_visible("production"):
            items.extend(self._recent_productions())
        if self._module_visible("sales"):
            items.extend(self._recent_sales())
        if self._module_visible("costs"):
            items.extend(self._recent_costs())
        items.sort(key=lambda item: item["sort_key"], reverse=True)
        for item in items:
            item.pop("sort_key", None)
        return items[:10]

    def _recent_sow_events(self) -> list[dict]:
        events = self.sow_activity_provider.recent_events(limit=5)
        return [
            self._event_item(
                date_value=event.event_date,
                type_label=event.get_event_type_display(),
                title=f"Maciora {event.sow.ear_tag}",
                description=f"Zdarzenie: {event.get_event_type_display()}",
                url=reverse("sow_detail", args=[event.sow_id]),
                icon_name="sow",
                sort_value=event.created_at,
            )
            for event in events
        ]

    def _recent_mortality_events(self) -> list[dict]:
        reports = self.sow_activity_provider.recent_mortality(limit=5)
        return [
            self._event_item(
                date_value=report.mortality_date,
                type_label="Upadek",
                title=report.get_mortality_type_display(),
                description=self._mortality_description(report),
                url=reverse("mortality_list"),
                icon_name="warning",
                sort_value=report.created_at,
            )
            for report in reports
        ]

    def _recent_deliveries(self) -> list[dict]:
        deliveries = self.feed_provider.recent_deliveries(limit=5)
        return [
            self._event_item(
                date_value=delivery.date,
                type_label="Dostawa",
                title=delivery.ingredient.name,
                description=format_mass(delivery.quantity_kg),
                url=reverse("edit_delivery", args=[delivery.id]),
                icon_name="warehouse",
                sort_value=delivery.date,
            )
            for delivery in deliveries
        ]

    def _recent_productions(self) -> list[dict]:
        productions = self.feed_provider.recent_productions(limit=5)
        return [
            self._event_item(
                date_value=production.date,
                type_label="Śrutowanie",
                title=production.recipe.name,
                description=f"{format_mass(production.quantity_kg)} · {production.status_label}",
                url=reverse("edit_production", args=[production.id]),
                icon_name="production",
                sort_value=production.created_at,
            )
            for production in productions
        ]

    def _recent_sales(self) -> list[dict]:
        sales = self.sales_provider.recent(limit=5)
        return [
            self._event_item(
                date_value=sale.sale_date,
                type_label="Sprzedaż",
                title=sale.document_number or f"{sale.quantity} szt.",
                description=f"{sale.net_value} zł netto",
                url=reverse("edit_sale", args=[sale.id]),
                icon_name="sales",
                sort_value=sale.created_at,
            )
            for sale in sales
        ]

    def _recent_costs(self) -> list[dict]:
        costs = self.cost_provider.recent(limit=5)
        return [
            self._event_item(
                date_value=cost.date,
                type_label="Koszt",
                title=cost.description,
                description=f"{cost.amount} zł",
                url=reverse("edit_cost", args=[cost.id]),
                icon_name="costs",
                sort_value=cost.created_at,
            )
            for cost in costs
        ]

    def _full_links(self) -> list[dict]:
        explicit_links = [
            ("sows", "Maciory", "Pełna lista macior", reverse("dashboard"), "sow"),
            ("statistics", "Statystyki", "Pełne statystyki", reverse("farm_statistics"), "statistics"),
            ("inventory", "Magazyn", "Pełny magazyn", reverse("feed_full_inventory"), "warehouse"),
            ("sales", "Sprzedaż", "Pełna sprzedaż", reverse("sales_list"), "sales"),
            ("costs", "Koszty", "Pełne koszty", reverse("cost_list"), "costs"),
        ]
        links = [
            {"title": title, "description": description, "url": url, "icon_name": icon_name}
            for module_key, title, description, url, icon_name in explicit_links
            if self._module_visible(module_key)
        ]
        visible_modules = ModuleNavigationService(self.farm).modules()
        visible_keys = {module["key"] for module in visible_modules}
        if "settings" in visible_keys:
            links.append({
                "title": "Ustawienia",
                "description": "Widoczność modułów i reguły gospodarstwa",
                "url": reverse("farm_settings"),
                "icon_name": "settings",
            })
        return links

    def _task_summary(self) -> dict:
        if self._tasks is None:
            self._tasks = TaskCenterService(self.farm).get_tasks()
        return self._tasks

    def _sow_summary(self) -> dict:
        if self._sows is None:
            self._sows = SowDashboardService(farm=self.farm).get_dashboard_summary()
        return self._sows

    def _inventory_summary(self) -> dict:
        if self._inventory is None:
            self._inventory = self.feed_provider.inventory()
        return self._inventory

    def _mortality_month_total(self) -> int:
        return self.sow_activity_provider.mortality_total_between(self.month_start, self.today)

    def _production_in_progress_count(self) -> int:
        return self.feed_provider.in_progress_count()

    def _sales_net_this_month(self) -> Decimal:
        return self.sales_provider.net_between(self.month_start, self.today)

    def _costs_this_month(self) -> Decimal:
        return self.cost_provider.total_between(self.month_start, self.today)

    def _module_visible(self, module_key: str | None) -> bool:
        return bool(module_key) and module_key in self.visible_keys

    def _event_item(
        self,
        *,
        date_value,
        type_label: str,
        title: str,
        description: str,
        url: str,
        icon_name: str,
        sort_value=None,
    ) -> dict:
        return {
            "date": date_value,
            "type_label": type_label,
            "title": title,
            "description": description,
            "url": url,
            "icon_name": icon_name,
            "sort_key": self._sort_key(sort_value or date_value),
        }

    @staticmethod
    def _mortality_description(report) -> str:
        if report.sow_id:
            return f"Maciora {report.sow.ear_tag} · {report.quantity} szt."
        return f"{report.quantity} szt. · {report.get_mortality_type_display()}"

    @staticmethod
    def _sort_key(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return timezone.make_aware(datetime.combine(value, time.min))
        return timezone.now()
