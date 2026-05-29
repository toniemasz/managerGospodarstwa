# sows/application/services.py
from datetime import date
from collections import defaultdict
from sows.infrastructure.repositories import SowRepository
from sows.models import VaccinationPlanModel


class SowDashboardService:
    """Serwis przygotowujący pełne statystyki oraz alerty (USG i szczepienia) dla panelu głównego."""

    def __init__(self, repository: SowRepository = None):
        self.repository = repository or SowRepository()

    def get_dashboard_summary(self) -> dict:
        today = date.today()
        sows = self.repository.get_all_sows()

        # Pobranie słownika planów szczepień z bazy danych
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
