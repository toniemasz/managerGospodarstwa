import logging
from datetime import date, timedelta
from collections import defaultdict

from sows.services.sow_metrics import METRICS_REGISTRY, MetricDescriptor
from sows.services.sow_repository import SowRepository
from sows.models import VaccinationPlanModel

logger = logging.getLogger(__name__)


class SowDashboardService:
    """Serwis przygotowujący pełne statystyki oraz alerty (USG i szczepienia) dla panelu głównego."""

    def __init__(self, farm=None, repository: SowRepository = None):
        self.farm = farm
        self.repository = repository or SowRepository(farm=farm)

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

        # Pobranie słownika planów szczepień z bazy danych
        db_plans = VaccinationPlanModel.objects.all()
        if self.farm is not None:
            db_plans = db_plans.filter(farm=self.farm)
        plans = self._build_vaccination_plans(db_plans)

        sows_to_check_usg = []
        vaccination_groups = defaultdict(list)

        status_counts = self._empty_status_counts()

        for sow in sows:
            try:
                sow.update_state_for_date(today)
                self._classify_sow_status(sow, status_counts)
                self._check_pregnancy_requirements(sow, sows_to_check_usg)
                self._group_vaccinations(sow, plans, vaccination_groups, today)
            except Exception as e:
                logger.exception("Błąd przetwarzania maciory %s (ID: %s): %s", sow.ear_tag, sow.id, e)

        return {
            'total_sows': len(sows),
            'inseminated_count': status_counts['inseminated_count'],
            'pregnant_count': status_counts['pregnant_count'],
            'lactating_count': status_counts['lactating_count'],
            'idle_count': status_counts['idle_count'],
            'to_recheck_count': status_counts['to_recheck_count'],
            'sows_to_check_usg': sows_to_check_usg,
            'vaccination_groups': dict(vaccination_groups),
            'all_sows': sows,
        }

    def get_archived_sows_list(self) -> list:
        """Pobiera i aktualizuje statusy dla zarchiwizowanych macior."""
        sows = self.repository.get_archived_sows()
        for sow in sows:
            try:
                sow.update_state_for_date(date.today())
            except Exception as e:
                logger.exception("Błąd przetwarzania zarchiwizowanej maciory %s: %s", sow.ear_tag, e)
        return sows

    @staticmethod
    def _build_vaccination_plans(db_plans) -> list:
        """Konwertuje modele planów szczepień na słowniki z wartościami domyślnymi."""
        plans = []
        for plan in db_plans:
            plans.append({
                'id': plan.id,
                'name': plan.name,
                'days_before_farrowing': plan.days_before_farrowing,
                'days_after_event': getattr(plan, 'days_after_event', None),
                'event_source': getattr(plan, 'event_source', None),
                'interval_months': plan.interval_months,
                'reminder_days_ahead': getattr(plan, 'reminder_days_ahead', 7)
            })
        return plans

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

    @staticmethod
    def _check_pregnancy_requirements(sow, sows_to_check_usg: list) -> None:
        """Sprawdza czy maciora wymaga badania USG."""
        if sow.status == "TO_CHECK":
            sows_to_check_usg.append(sow)

    @staticmethod
    def _group_vaccinations(sow, plans: list, vaccination_groups: dict, current_date: date) -> None:
        """Grupuje szczepienia dla maciory na podstawie planów."""
        for plan_dict in plans:
            vacc_status = sow.get_vaccination_status(plan_dict, current_date=current_date)
            if vacc_status['should_display']:
                group_key = f"{plan_dict['name']} (Termin: {vacc_status['target_date'].strftime('%d.%m.%Y')})"
                vaccination_groups[group_key].append({
                    'sow_id': sow.id,
                    'ear_tag': sow.ear_tag,
                    'status_display': sow.dynamic_status_display,
                    'cycle_id': vacc_status['cycle_id'],
                    'vaccine_name': plan_dict['name'],
                    'is_eligible': vacc_status['is_eligible']
                })

    def get_general_statistics(self, metric_key: str, months_limit: int = 6, order: str = 'desc') -> dict:
        """Generuje modularne statystyki okresowe oraz ranking dla wybranej metryki."""
        if metric_key not in METRICS_REGISTRY:
            metric_key = list(METRICS_REGISTRY.keys())[0]

        metric: MetricDescriptor = METRICS_REGISTRY[metric_key]
        sows = self.repository.get_all_sows()

        monthly_data = defaultdict(int)
        top_sows_list = []

        if months_limit == 0:
            cutoff_date = date.min
        else:
            cutoff_date = date.today() - timedelta(days=months_limit * 30)

        for sow in sows:
            sow_total = 0
            for event in sow.all_events:
                if event.event_type == metric.event_type and event.event_date >= cutoff_date:
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
