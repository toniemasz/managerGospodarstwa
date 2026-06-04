# sows/application/services.py
from datetime import date, timedelta
from collections import defaultdict
from django.utils import timezone

from sows.application.metrics import METRICS_REGISTRY, MetricDescriptor
from sows.infrastructure.repositories import SowRepository
from sows.models import VaccinationPlanModel, SowModel, SowEventModel


class SowManagementService:
    """Serwis odpowiedzialny za logikę tworzenia, aktualizacji i usuwania danych."""

    @staticmethod
    def create_sow(form_data: dict) -> SowModel:
        return SowModel.objects.create(**form_data)

    @staticmethod
    def update_sow(sow_id: int, form_data: dict) -> SowModel:
        sow = SowModel.objects.get(id=sow_id)
        for field, value in form_data.items():
            setattr(sow, field, value)
        sow.save()
        return sow

    @staticmethod
    def delete_or_archive_sow(sow_id: int, is_archived: bool) -> None:
        sow = SowModel.objects.get(id=sow_id)
        if is_archived:
            sow.is_archived = True
            sow.archived_at = timezone.now()
            sow.save()
        else:
            sow.delete()

    @staticmethod
    def create_vaccination_plan(form_data: dict) -> VaccinationPlanModel:
        return VaccinationPlanModel.objects.create(**form_data)

    @staticmethod
    def create_sow_event(sow_id: int, form_data: dict) -> SowEventModel:
        sow = SowModel.objects.get(id=sow_id)
        return SowEventModel.objects.create(sow=sow, **form_data)

    @staticmethod
    def update_sow_event(event_id: int, form_data: dict) -> SowEventModel:
        event = SowEventModel.objects.get(id=event_id)
        for field, value in form_data.items():
            setattr(event, field, value)
        event.save()
        return event

    @staticmethod
    def delete_sow_event(event_id: int) -> int:
        """Usuwa zdarzenie i zwraca ID maciory (przydatne do przekierowania)."""
        event = SowEventModel.objects.get(id=event_id)
        sow_id = event.sow.id
        event.delete()
        return sow_id

    @staticmethod
    def bulk_pregnancy_check(check_results: dict) -> None:
        """Zapisuje masowe wyniki badań USG. Słownik wejściowy to {sow_id: result}."""
        for sow_id, result in check_results.items():
            if result in ['TAK', 'NIE', '?']:
                sow = SowModel.objects.get(id=sow_id)
                SowEventModel.objects.create(
                    sow=sow,
                    event_type='PREGNANCY_CHECK',
                    event_date=date.today(),
                    details={'result': result}
                )

    @staticmethod
    def bulk_vaccinate(sow_ids: list, vaccine_name: str, cycle_id: str) -> None:
        """Tworzy zdarzenia masowego szczepienia."""
        for s_id in sow_ids:
            sow = SowModel.objects.get(id=s_id)
            SowEventModel.objects.create(
                sow=sow,
                event_type='VACCINATION',
                event_date=date.today(),
                details={
                    'vaccine_name': vaccine_name,
                    'cycle_id': cycle_id
                }
            )

    @staticmethod
    def get_event_initial_data(db_event: SowEventModel) -> dict:
        """Przygotowuje dane początkowe formularza na podstawie typu zdarzenia."""
        event_details_mapping = {
            'INSEMINATION': {'technician': db_event.details.get('technician', '')},
            'PREGNANCY_CHECK': {'pregnancy_result': db_event.details.get('result', '')},
            'FARROWING': {
                'born_alive': db_event.details.get('born_alive', 0),
                'born_dead': db_event.details.get('born_dead', 0)
            },
            'WEANING': {'count': db_event.details.get('count', 0)},
            'VACCINATION': {'vaccine_name': db_event.details.get('vaccine_name', '')},
        }
        return event_details_mapping.get(db_event.event_type, {})


class SowDashboardService:
    """Serwis przygotowujący pełne statystyki oraz alerty (USG i szczepienia) dla panelu głównego."""

    def __init__(self, repository: SowRepository = None):
        self.repository = repository or SowRepository()

    def get_dashboard_summary(self) -> dict:
        today = date.today()
        sows = self.repository.get_all_sows()

        db_plans = VaccinationPlanModel.objects.all()
        plans = self._build_vaccination_plans(db_plans)

        sows_to_check_usg = []
        vaccination_groups = defaultdict(list)

        status_counts = {
            'inseminated_count': 0,
            'pregnant_count': 0,
            'lactating_count': 0,
            'idle_count': 0,
            'to_recheck_count': 0,
            'to_check_count': 0,
        }

        for sow in sows:
            try:
                sow.update_state_for_date(today)
                self._classify_sow_status(sow, status_counts)
                self._check_pregnancy_requirements(sow, sows_to_check_usg)
                self._group_vaccinations(sow, plans, vaccination_groups, today)
            except Exception as e:
                print(f"Błąd przetwarzania maciory {sow.ear_tag} (ID: {sow.id}): {e}")

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
        sows = self.repository.get_archived_sows()
        for sow in sows:
            try:
                sow.update_state_for_date(date.today())
            except Exception as e:
                print(f"Błąd przetwarzania zarchiwizowanej maciory {sow.ear_tag}: {e}")
        return sows

    @staticmethod
    def _build_vaccination_plans(db_plans) -> list:
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
        if sow.status == "TO_CHECK":
            sows_to_check_usg.append(sow)

    @staticmethod
    def _group_vaccinations(sow, plans: list, vaccination_groups: dict, current_date: date) -> None:
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

            if sow_total > 0 or sow.status != "ARCHIVED":
                top_sows_list.append({
                    'id': sow.id,
                    'ear_tag': sow.ear_tag,
                    'total_value': sow_total,
                    'status': sow.dynamic_status_display
                })

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