from __future__ import annotations

from datetime import date

from sows.domain.rules import FARROWING_ALERT_DAYS_AHEAD, PREGNANCY_CHECK_AFTER_DAYS
from sows.services.vaccination_schedule import VaccinationScheduleService


class SowNotificationService:
    def __init__(
        self,
        farm=None,
        *,
        pregnancy_check_after_days: int = PREGNANCY_CHECK_AFTER_DAYS,
        farrowing_alert_days_ahead: int = FARROWING_ALERT_DAYS_AHEAD,
    ):
        self.farm = farm
        self.pregnancy_check_after_days = pregnancy_check_after_days
        self.farrowing_alert_days_ahead = farrowing_alert_days_ahead

    def build_notifications(self, sows: list, current_date: date) -> dict:
        sows_to_check_usg = []
        farrowing_due_sows = []

        for sow in sows:
            if sow.status == "TO_CHECK" or sow.is_due_for_pregnancy_check(
                current_date,
                pregnancy_check_after_days=self.pregnancy_check_after_days,
            ):
                sows_to_check_usg.append(sow)

            due_record = self._farrowing_due_record(sow, current_date)
            if due_record:
                farrowing_due_sows.append(due_record)

        vaccination_groups = (
            VaccinationScheduleService(self.farm).build_groups(sows, current_date)
            if self.farm is not None
            else {}
        )

        return {
            'sows_to_check_usg': sows_to_check_usg,
            'farrowing_due_sows': farrowing_due_sows,
            'farrowing_due_count': len(farrowing_due_sows),
            'vaccination_groups': vaccination_groups,
            'vaccinations_due_count': sum(len(items) for items in vaccination_groups.values()),
        }

    def _farrowing_due_record(self, sow, current_date: date) -> dict | None:
        if not sow.expected_farrowing_date:
            return None
        days_to_farrowing = (sow.expected_farrowing_date - current_date).days
        if days_to_farrowing > self.farrowing_alert_days_ahead:
            return None

        if days_to_farrowing > 0:
            alert_status = "upcoming"
            alert_status_label = "Zbliża się"
            time_label = f"za {days_to_farrowing} dni"
            priority = "upcoming"
        elif days_to_farrowing == 0:
            alert_status = "today"
            alert_status_label = "Dzisiaj"
            time_label = "dzisiaj"
            priority = "today"
        else:
            days_overdue = abs(days_to_farrowing)
            alert_status = "overdue"
            alert_status_label = "Po terminie"
            time_label = f"{days_overdue} dni po terminie"
            priority = "urgent"

        return {
            'id': sow.id,
            'ear_tag': sow.ear_tag,
            'expected_farrowing_date': sow.expected_farrowing_date,
            'days_to_farrowing': days_to_farrowing,
            'days_overdue': abs(days_to_farrowing) if days_to_farrowing < 0 else 0,
            'alert_status': alert_status,
            'alert_status_label': alert_status_label,
            'time_label': time_label,
            'priority': priority,
            'status': sow.status,
            'status_display': sow.dynamic_status_display,
            'detail_url_name': 'sow_detail',
        }
