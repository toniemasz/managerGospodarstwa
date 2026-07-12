from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from costs.dashboard import CostDashboardProvider
from common.cache import TASK_CENTER_TTL, cached_farm_value
from feed.services.dashboard import FeedDashboardProvider
from sales.dashboard import SalesDashboardProvider
from sows.services.sow_dashboard_service import SowDashboardService
from common.units import format_mass


class TaskCenterService:
    """Buduje gotowy do prezentacji, wspólny model wszystkich aktywnych zadań."""

    def __init__(self, farm):
        self.farm = farm
        self.today = timezone.localdate()
        self._low_stock = []
        self._unsettled_sales = []
        self.feed_provider = FeedDashboardProvider(farm)
        self.sales_provider = SalesDashboardProvider(farm)
        self.cost_provider = CostDashboardProvider(farm)

    @staticmethod
    def _task(
        *,
        title,
        description,
        status_label,
        priority,
        due_date=None,
        object_url=None,
        action_url=None,
        action_label=None,
        metadata=None,
    ) -> dict:
        return {
            "title": title,
            "description": description,
            "status_label": status_label,
            "priority": priority,
            "due_date": due_date,
            "object_url": object_url,
            "action_url": action_url,
            "action_label": action_label,
            "metadata": metadata or {},
        }

    @staticmethod
    def _section(key, title, items, empty_message, panel_url, panel_label="Otwórz panel") -> dict:
        urgent_count = sum(item["priority"] in {"urgent", "today"} for item in items)
        return {
            "key": key,
            "title": title,
            "count": len(items),
            "items": items,
            "preview_items": items[:3],
            "more_count": max(0, len(items) - 3),
            "urgent_count": urgent_count,
            "panel_url": panel_url,
            "panel_label": panel_label,
            "empty_message": empty_message,
        }

    @staticmethod
    def _tab(key, title, sections, empty_message) -> dict:
        items = [item for section in sections for item in section["items"]]
        return {
            "key": key,
            "title": title,
            "count": len(items),
            "sections": sections,
            "items": items,
            "empty_message": empty_message,
            "urgent_count": sum(section["urgent_count"] for section in sections),
        }

    def _production_tab(self) -> dict:
        notifications = SowDashboardService(farm=self.farm).get_notifications(
            current_date=self.today,
        )

        ultrasound_items = [
            self._task(
                title=f"USG maciory {sow.ear_tag}",
                description=f"Status stada: {sow.dynamic_status_display}.",
                status_label="Do wykonania",
                priority="urgent",
                object_url=reverse("sow_detail", args=[sow.id]),
                action_url=reverse("bulk_pregnancy_check"),
                action_label="Dodaj wynik USG",
                metadata={"sow_id": sow.id, "kind": "ultrasound"},
            )
            for sow in notifications["sows_to_check_usg"]
        ]

        farrowing_items = [
            self._task(
                title=f"Oproszenie maciory {item['ear_tag']}",
                description=(
                    "Planowany termin: "
                    f"{item['expected_farrowing_date'].strftime('%d.%m.%Y')} — "
                    f"{item['alert_status_label'].lower()}."
                ),
                status_label=item["time_label"],
                priority=item["priority"],
                due_date=item["expected_farrowing_date"],
                object_url=reverse("sow_detail", args=[item["id"]]),
                action_url=(
                    f"{reverse('add_event', args=[item['id']])}?event_type=FARROWING"
                ),
                action_label="Dodaj oproszenie",
                metadata={
                    "sow_id": item["id"],
                    "kind": "farrowing",
                    "alert_status": item["alert_status"],
                },
            )
            for item in notifications["farrowing_due_sows"]
        ]

        vaccination_items = []
        for group_items in notifications["vaccination_groups"].values():
            for item in group_items:
                days_to_target = item["days_to_target"]
                if days_to_target < 0:
                    status_label = f"{abs(days_to_target)} dni po terminie"
                    priority = "urgent"
                elif days_to_target == 0:
                    status_label = "dzisiaj"
                    priority = "today"
                else:
                    status_label = f"za {days_to_target} dni"
                    priority = "upcoming"
                vaccination_items.append(
                    self._task(
                        title=f"Szczepienie maciory {item['ear_tag']}",
                        description=f"Preparat: {item['vaccine_name']}.",
                        status_label=status_label,
                        priority=priority,
                        due_date=item["target_date"],
                        object_url=reverse("sow_detail", args=[item["sow_id"]]),
                        action_url=reverse("bulk_vaccinate"),
                        action_label="Potwierdź szczepienie",
                        metadata={
                            "sow_id": item["sow_id"],
                            "kind": "vaccination",
                            "vaccine_name": item["vaccine_name"],
                            "cycle_id": item["cycle_id"],
                            "plan_id": item["plan_id"],
                            "scheduled_date": item["scheduled_date"].isoformat(),
                        },
                    )
                )

        sections = [
            self._section("ultrasound", "Badania USG", ultrasound_items, "Brak badań USG do wykonania.", reverse("bulk_pregnancy_check"), "Panel badań USG"),
            self._section("vaccination", "Szczepienia", vaccination_items, "Brak szczepień do wykonania.", reverse("bulk_vaccinate"), "Panel szczepień"),
            self._section("farrowing", "Oproszenia", farrowing_items, "Brak zaplanowanych oproszeń.", reverse("farrowing_panel"), "Panel oproszeń"),
        ]
        return self._tab(
            "production",
            "Produkcja",
            sections,
            "W produkcji nie ma teraz zadań wymagających uwagi.",
        )

    def _feed_tab(self) -> dict:
        inventory = self.feed_provider.inventory()
        self._low_stock = inventory["low_stock_alerts"]
        low_stock_items = [
            self._task(
                title=f"Niski stan: {item.name}",
                description=(
                    f"Pozostało {format_mass(item.current_stock)}; próg alertu "
                    f"to {format_mass(item.low_stock_threshold_kg)}."
                ),
                status_label="niski stan",
                priority="urgent",
                object_url=reverse("feed_inventory"),
                action_url=reverse("add_delivery"),
                action_label="Dodaj dostawę",
                metadata={"ingredient_id": item.ingredient_id, "kind": "low_stock"},
            )
            for item in inventory["low_stock_alerts"]
        ]

        queued = self.feed_provider.queued()
        queued_items = [
            self._task(
                title=f"Śrutowanie: {production.recipe.name}",
                description=f"Zaplanowano {format_mass(production.quantity_kg)} paszy.",
                status_label="w kolejce",
                priority="upcoming",
                due_date=production.date,
                object_url=reverse("edit_production", args=[production.id]),
                action_url=reverse("process_stage1", args=[production.id]),
                action_label="Rozpocznij etap 1",
                metadata={"production_id": production.id, "kind": "production_queued"},
            )
            for production in queued
        ]

        stage_one = self.feed_provider.stage_one_done()
        stage_one_items = [
            self._task(
                title=f"Dokończ śrutowanie: {production.recipe.name}",
                description=f"Etap 1 ukończony dla {format_mass(production.quantity_kg)} paszy.",
                status_label="etap 2",
                priority="today",
                due_date=production.date,
                object_url=reverse("edit_production", args=[production.id]),
                action_url=reverse("process_stage2", args=[production.id]),
                action_label="Wykonaj etap 2",
                metadata={"production_id": production.id, "kind": "production_stage_2"},
            )
            for production in stage_one
        ]

        sections = [
            self._section("low_stock", "Niskie stany magazynowe", low_stock_items, "Stany magazynowe są bezpieczne.", reverse("feed_inventory"), "Otwórz magazyn"),
            self._section("queued", "Śrutowania w kolejce", queued_items, "Kolejka śrutowań jest pusta.", reverse("feed_productions"), "Otwórz kolejkę"),
            self._section("stage_one", "Śrutowania po etapie 1", stage_one_items, "Brak śrutowań oczekujących na etap 2.", reverse("feed_productions"), "Otwórz śrutowanie"),
        ]
        return self._tab(
            "feed",
            "Magazyn i pasza",
            sections,
            "Magazyn i produkcja paszy nie wymagają teraz uwagi.",
        )

    def _finance_tab(self) -> dict:
        sales = self.sales_provider.unsettled()
        self._unsettled_sales = list(sales)
        sale_items = [
            self._task(
                title=f"Sprzedaż bez rozliczenia: {sale.sale_date:%d.%m.%Y}",
                description=f"Sprzedano {sale.quantity} szt.; uzupełnij dane rozliczenia.",
                status_label="do rozliczenia",
                priority="urgent",
                due_date=sale.sale_date,
                object_url=reverse("edit_sale", args=[sale.id]),
                action_url=reverse("edit_sale", args=[sale.id]),
                action_label="Uzupełnij sprzedaż",
                metadata={"sale_id": sale.id, "kind": "unsettled_sale"},
            )
            for sale in self._unsettled_sales
        ]

        costs = self.cost_provider.attention_costs()
        cost_items = []
        for cost in costs:
            issues = []
            if cost.category_id is None:
                issues.append("brak kategorii")
            if not cost.is_paid:
                issues.append("nieopłacony")
            cost_items.append(
                self._task(
                    title=f"Koszt wymaga uwagi: {cost.description}",
                    description=f"{cost.amount:.2f} zł — {', '.join(issues)}.",
                    status_label="wymaga uzupełnienia",
                    priority="upcoming" if cost.is_paid else "urgent",
                    due_date=cost.date,
                    object_url=reverse("edit_cost", args=[cost.id]),
                    action_url=reverse("edit_cost", args=[cost.id]),
                    action_label="Uzupełnij koszt",
                    metadata={"cost_id": cost.id, "kind": "cost_attention"},
                )
            )

        sections = [
            self._section("unsettled_sales", "Sprzedaże bez rozliczenia", sale_items, "Wszystkie sprzedaże są rozliczone.", reverse("sales_list"), "Otwórz sprzedaż"),
            self._section("costs", "Koszty wymagające uwagi", cost_items, "Wszystkie koszty są kompletne i opłacone.", reverse("cost_list"), "Otwórz koszty"),
        ]
        return self._tab(
            "finance",
            "Finanse",
            sections,
            "Finanse nie mają teraz zadań wymagających uwagi.",
        )

    def get_tasks(self) -> dict:
        result = cached_farm_value(
            self.farm,
            "task_center",
            (self.today,),
            timeout=TASK_CENTER_TTL,
            builder=self._build_tasks,
        )
        self._low_stock = result.get("low_stock", [])
        self._unsettled_sales = result.get("unsettled_sales", [])
        return result

    def _build_tasks(self) -> dict:
        tabs = {
            "production": self._production_tab(),
            "feed": self._feed_tab(),
            "finance": self._finance_tab(),
        }
        result = {
            "tabs": tabs,
            "tab_list": list(tabs.values()),
            "task_count": sum(tab["count"] for tab in tabs.values()),
        }
        # Klucze zgodności zachowują stabilne API dla integracji serwisowych.
        result["low_stock"] = self._low_stock
        result["unsettled_sales"] = self._unsettled_sales
        return result
