from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sows.domain.vaccinations import add_vaccination_interval, vaccination_cycle_id
from sows.models import VaccinationCycleModel, VaccinationPlanModel


class VaccinationScheduleService:
    """Jedyne źródło prawdy dla terminów i bieżących cykli szczepień."""

    def __init__(self, farm):
        if farm is None:
            raise ValueError("Harmonogram szczepień wymaga jawnego gospodarstwa.")
        self.farm = farm

    def build_groups(self, sows: list, current_date: date) -> dict[str, list[dict]]:
        groups = defaultdict(list)
        for reminder in self.build_reminders(sows, current_date):
            key = f"{reminder['vaccine_name']} (Termin: {reminder['target_date']:%d.%m.%Y})"
            groups[key].append(reminder)
        return dict(groups)

    def build_reminders(
        self,
        sows: list,
        current_date: date,
        *,
        plan_ids: set[int] | None = None,
    ) -> list[dict]:
        plans = self._plans(plan_ids)
        reminders = []
        for plan in plans:
            selected_ids = {sow.id for sow in plan.selected_sows.all()}
            excluded_ids = {sow.id for sow in plan.excluded_sows.all()}
            states_by_sow = defaultdict(dict)
            for state in plan.cycle_records.all():
                states_by_sow[state.sow_id][state.cycle_id] = state

            for sow in sows:
                if not self._covers_sow(plan, sow.id, selected_ids, excluded_ids):
                    continue
                reminder = self._reminder_for_sow(
                    plan,
                    sow,
                    states_by_sow.get(sow.id, {}),
                    current_date,
                )
                if reminder:
                    reminders.append(reminder)
        return reminders

    def current_reminder(self, *, sow, plan_id: int, current_date: date) -> dict | None:
        reminders = self.build_reminders([sow], current_date, plan_ids={plan_id})
        return reminders[0] if reminders else None

    def active_plans_for_sow(self, sow_id: int) -> list[VaccinationPlanModel]:
        """Zwraca aktywne plany, które obejmują wskazaną maciorę."""
        plans = self._plans(None)
        return [
            plan
            for plan in plans
            if self._covers_sow(
                plan,
                sow_id,
                {sow.id for sow in plan.selected_sows.all()},
                {sow.id for sow in plan.excluded_sows.all()},
            )
        ]

    def _plans(self, plan_ids: set[int] | None):
        queryset = VaccinationPlanModel.objects.filter(
            farm=self.farm,
            is_active=True,
            requires_configuration=False,
        ).prefetch_related("selected_sows", "excluded_sows", "cycle_records")
        if plan_ids is not None:
            queryset = queryset.filter(id__in=plan_ids)
        return list(queryset.order_by("name", "id"))

    @staticmethod
    def _covers_sow(plan, sow_id: int, selected_ids: set[int], excluded_ids: set[int]) -> bool:
        if sow_id in excluded_ids:
            return False
        if plan.scope == VaccinationPlanModel.SCOPE_SELECTED:
            return sow_id in selected_ids
        return True

    def _reminder_for_sow(self, plan, sow, states: dict, current_date: date) -> dict | None:
        if plan.interval_value or plan.interval_months:
            target_date, cycle_id = self._periodic_cycle(plan, sow, states)
        else:
            target_date, cycle_id = self._legacy_event_cycle(plan, sow)

        if not target_date or not cycle_id or cycle_id in states:
            return None
        days_to_target = (target_date - current_date).days
        if days_to_target > plan.reminder_days_ahead:
            return None

        if days_to_target < 0:
            status = "overdue"
            status_label = "Zaległe"
        elif days_to_target == 0:
            status = "today"
            status_label = "Dzisiaj"
        else:
            status = "upcoming"
            status_label = "Nadchodzące"

        return {
            "plan_id": plan.id,
            "sow_id": sow.id,
            "ear_tag": sow.ear_tag,
            "status_display": sow.dynamic_status_display,
            "cycle_id": cycle_id,
            "vaccine_name": plan.name,
            "target_date": target_date,
            "scheduled_date": target_date,
            "days_to_target": days_to_target,
            "status": status,
            "status_label": status_label,
            "is_eligible": days_to_target <= 0,
        }

    def _periodic_cycle(self, plan, sow, states: dict) -> tuple[date | None, str | None]:
        value = plan.interval_value or plan.interval_months
        unit = plan.interval_unit or VaccinationPlanModel.INTERVAL_MONTHS
        if not value:
            return None, None

        target_date = plan.first_due_date
        if target_date is None:
            last_event = self._last_completed_event(plan, sow)
            if last_event is None:
                return None, None
            target_date = add_vaccination_interval(last_event.event_date, value, unit)

        while True:
            cycle_id = vaccination_cycle_id(plan.id, target_date)
            state = states.get(cycle_id)
            if state is None:
                return target_date, cycle_id
            if plan.schedule_mode == VaccinationPlanModel.SCHEDULE_FIXED:
                base_date = target_date
            elif state.status == VaccinationCycleModel.STATUS_COMPLETED:
                base_date = state.completed_at or state.scheduled_date
            else:
                base_date = state.scheduled_date
            target_date = add_vaccination_interval(base_date, value, unit)

    @staticmethod
    def _last_completed_event(plan, sow):
        matching = [
            event
            for event in sow.vaccinations
            if event.vaccination_plan_id == plan.id
            or (
                event.vaccination_plan_id is None
                and event.details.get("vaccine_name") == plan.name
            )
        ]
        return max(matching, key=lambda event: (event.event_date, event.id or 0)) if matching else None

    @staticmethod
    def _legacy_event_cycle(plan, sow) -> tuple[date | None, str | None]:
        if plan.days_before_farrowing is not None and sow.expected_farrowing_date:
            return (
                sow.expected_farrowing_date - timedelta(days=plan.days_before_farrowing),
                f"farrowing_{sow.expected_farrowing_date.isoformat()}",
            )
        if plan.days_after_event is None or not plan.event_source:
            return None, None
        if plan.event_source == "FARROWING" and sow.last_farrowing_date:
            return (
                sow.last_farrowing_date + timedelta(days=plan.days_after_event),
                f"after_farrowing_{sow.last_farrowing_date.isoformat()}",
            )
        if plan.event_source == "INSEMINATION" and sow.last_insemination_date:
            return (
                sow.last_insemination_date + timedelta(days=plan.days_after_event),
                f"after_insemination_{sow.last_insemination_date.isoformat()}",
            )
        return None, None
