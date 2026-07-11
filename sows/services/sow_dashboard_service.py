import logging
from datetime import date, timedelta
from collections import defaultdict

from farms.services.settings_service import get_farm_settings
from sows.domain.rules import FARROWING_ALERT_DAYS_AHEAD, PREGNANCY_CHECK_AFTER_DAYS
from sows.services.sow_metrics import METRICS_REGISTRY, MetricDescriptor
from sows.services.sow_repository import SowRepository
from sows.services.sow_notification_service import SowNotificationService

logger = logging.getLogger(__name__)


class SowDashboardService:
    """Serwis przygotowujący pełne statystyki oraz alerty (USG i szczepienia) dla panelu głównego."""

    def __init__(self, farm=None, repository: SowRepository = None):
        if farm is None and repository is None:
            raise ValueError("Dashboard macior wymaga jawnego gospodarstwa.")
        self.farm = farm
        self.repository = repository or SowRepository(farm=farm)
        self.settings = get_farm_settings(farm) if farm is not None else None

    @staticmethod
    def _empty_status_counts() -> dict:
        return {
            'inseminated_count': 0,
            'pregnant_count': 0,
            'lactating_count': 0,
            'idle_count': 0,
            'to_recheck_count': 0,
            'to_check_count': 0,
        }

    def get_dashboard_summary(self) -> dict:
        today = date.today()
        sows = self.repository.get_all_sows()

        status_counts = self._empty_status_counts()
        pregnancy_check_after_days = self._pregnancy_check_after_days()

        for sow in sows:
            try:
                sow.update_state_for_date(today, pregnancy_check_after_days=pregnancy_check_after_days)
                self._classify_sow_status(sow, status_counts)
            except Exception as e:
                logger.exception("Błąd przetwarzania maciory %s (ID: %s): %s", sow.ear_tag, sow.id, e)

        notifications = self.get_notifications(
            sows=sows,
            current_date=today,
            update_states=False,
        )
        self._attach_operational_notes(sows, notifications)

        return {
            'total_sows': len(sows),
            'inseminated_count': status_counts['inseminated_count'],
            'pregnant_count': status_counts['pregnant_count'],
            'lactating_count': status_counts['lactating_count'],
            'idle_count': status_counts['idle_count'],
            'to_recheck_count': status_counts['to_recheck_count'],
            'sows_to_check_usg': notifications['sows_to_check_usg'],
            'farrowing_due_sows': notifications['farrowing_due_sows'],
            'farrowing_due_count': notifications['farrowing_due_count'],
            'vaccination_groups': notifications['vaccination_groups'],
            'vaccinations_due_count': notifications['vaccinations_due_count'],
            'sow_attention_items': self._attention_items(notifications),
            'all_sows': sows,
        }

    def get_notifications(
        self,
        *,
        sows: list | None = None,
        current_date: date | None = None,
        update_states: bool = True,
    ) -> dict:
        """Zwraca wspólny zestaw alertów bez liczenia statystyk dashboardu."""
        current_date = current_date or date.today()
        sows = sows if sows is not None else self.repository.get_all_sows()
        pregnancy_check_after_days = self._pregnancy_check_after_days()

        if update_states:
            for sow in sows:
                try:
                    sow.update_state_for_date(
                        current_date,
                        pregnancy_check_after_days=pregnancy_check_after_days,
                    )
                except Exception as error:
                    logger.exception(
                        "Błąd przetwarzania alertów maciory %s (ID: %s): %s",
                        sow.ear_tag,
                        sow.id,
                        error,
                    )

        return SowNotificationService(
            farm=self.farm,
            pregnancy_check_after_days=pregnancy_check_after_days,
            farrowing_alert_days_ahead=self._farrowing_alert_days_ahead(),
        ).build_notifications(sows, current_date)

    def get_archived_sows_list(self) -> list:
        """Pobiera i aktualizuje statusy dla zarchiwizowanych macior."""
        sows = self.repository.get_archived_sows()
        for sow in sows:
            try:
                sow.update_state_for_date(
                    date.today(),
                    pregnancy_check_after_days=self._pregnancy_check_after_days(),
                )
            except Exception as e:
                logger.exception("Błąd przetwarzania zarchiwizowanej maciory %s: %s", sow.ear_tag, e)
        return sows

    @staticmethod
    def _classify_sow_status(sow, status_counts: dict) -> None:
        """Klasyfikuje status maciory i aktualizuje liczniki."""
        status_mapping = {
            'INSEMINATED': 'inseminated_count',
            'PREGNANT': 'pregnant_count',
            'LACTATING': 'lactating_count',
            'IDLE': 'idle_count',
            'TO_RECHECK': 'to_recheck_count',
            'TO_CHECK': 'to_check_count',
        }

        if sow.status in status_mapping:
            status_counts[status_mapping[sow.status]] += 1

    def _pregnancy_check_after_days(self) -> int:
        return self.settings.pregnancy_check_after_days if self.settings else PREGNANCY_CHECK_AFTER_DAYS

    def _farrowing_alert_days_ahead(self) -> int:
        return self.settings.farrowing_alert_days_ahead if self.settings else FARROWING_ALERT_DAYS_AHEAD

    def _attach_operational_notes(self, sows: list, notifications: dict) -> None:
        notes = {}
        for sow in notifications['sows_to_check_usg']:
            notes[sow.id] = {
                "label": "Wykonaj USG",
                "date": sow.last_insemination_date,
                "priority": "urgent",
                "url_name": "bulk_pregnancy_check",
            }
        for item in notifications['farrowing_due_sows']:
            notes.setdefault(item["id"], {
                "label": item["alert_status_label"],
                "date": item["expected_farrowing_date"],
                "priority": item["priority"],
                "url_name": "farrowing_panel",
            })
        for group_items in notifications['vaccination_groups'].values():
            for item in group_items:
                notes.setdefault(item["sow_id"], {
                    "label": f"Szczepienie: {item['vaccine_name']}",
                    "date": item["target_date"],
                    "priority": "urgent" if item["days_to_target"] <= 0 else "upcoming",
                    "url_name": "bulk_vaccinate",
                })

        for sow in sows:
            note = notes.get(sow.id, {})
            sow.operational_label = note.get("label", "Brak pilnych czynności")
            sow.operational_date = note.get("date")
            sow.operational_priority = note.get("priority", "")

    @staticmethod
    def _attention_items(notifications: dict) -> list[dict]:
        items = []
        items.extend({
            "title": f"USG maciory {sow.ear_tag}",
            "description": "Wpisz wynik badania, żeby status cyklu był aktualny.",
            "priority": "urgent",
        } for sow in notifications['sows_to_check_usg'][:3])
        items.extend({
            "title": f"Oproszenie maciory {item['ear_tag']}",
            "description": item["time_label"],
            "priority": item["priority"],
        } for item in notifications['farrowing_due_sows'][:3])
        for group_items in notifications['vaccination_groups'].values():
            for item in group_items[:2]:
                items.append({
                    "title": f"Szczepienie maciory {item['ear_tag']}",
                    "description": item["vaccine_name"],
                    "priority": "urgent" if item["days_to_target"] <= 0 else "upcoming",
                })
        priority_order = {"urgent": 0, "today": 1, "upcoming": 2}
        return sorted(items, key=lambda item: (priority_order.get(item["priority"], 9), item["title"]))[:5]

    def get_general_statistics(
        self,
        metric_key: str,
        months_limit: int = 6,
        order: str = 'desc',
        date_from=None,
        date_to=None,
    ) -> dict:
        """Generuje modularne statystyki okresowe oraz ranking dla wybranej metryki."""
        if metric_key not in METRICS_REGISTRY:
            metric_key = list(METRICS_REGISTRY.keys())[0]

        metric: MetricDescriptor = METRICS_REGISTRY[metric_key]
        sows = self.repository.get_all_sows()

        monthly_data = defaultdict(int)
        top_sows_list = []

        if date_from is not None or date_to is not None:
            cutoff_date = date_from or date.min
            end_date = date_to or date.max
        elif months_limit == 0:
            cutoff_date = date.min
            end_date = date.max
        else:
            cutoff_date = date.today() - timedelta(days=months_limit * 30)
            end_date = date.today()

        for sow in sows:
            sow_total = 0
            for event in sow.all_events:
                if event.event_type == metric.event_type and cutoff_date <= event.event_date <= end_date:
                    val = metric.value_extractor(event.details)
                    sow_total += val

                    month_key = event.event_date.strftime('%Y-%m')
                    monthly_data[month_key] += val

            # Wrzucamy do rankingu tylko jeśli były jakieś dane
            if sow_total > 0 or sow.status != "ARCHIVED":
                top_sows_list.append({
                    'id': sow.id,
                    'ear_tag': sow.ear_tag,
                    'total_value': sow_total,
                    'status': sow.dynamic_status_display
                })

        # Sortowanie na podstawie wybranego trybu
        reverse_sort = True if order == 'desc' else False
        top_sows_list = sorted(top_sows_list, key=lambda x: x['total_value'], reverse=reverse_sort)[:10]

        sorted_months = sorted(monthly_data.keys())
        chart_labels = sorted_months
        chart_values = [monthly_data[m] for m in sorted_months]

        return {
            'current_metric': metric,
            'available_metrics': METRICS_REGISTRY.values(),
            'current_months_limit': months_limit,
            'current_order': order,
            'top_sows': top_sows_list,
            'chart_labels': chart_labels,
            'chart_values': chart_values,
        }
