# sows/application/services.py
from datetime import date
from collections import defaultdict
from sows.infrastructure.repositories import SowRepository
from sows.models import VaccinationPlanModel

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

        sows_to_check_usg = []
        vaccination_groups = defaultdict(list)

        inseminated_count = 0
        pregnant_count = 0
        lactating_count = 0
        idle_count = 0
        to_recheck_count = 0
        to_check_count = 0

        for sow in sows:
            sow.update_state_for_date(today)
            # Klasyfikacja i zliczanie rozszerzonych statusów produkcyjnych
            # Klasyfikacja statusów
            if sow.status == "INSEMINATED":
                inseminated_count += 1
            elif sow.status == "PREGNANT":
                pregnant_count += 1
            elif sow.status == "LACTATING":
                lactating_count += 1
            elif sow.status == "IDLE":
                idle_count += 1
            elif sow.status == "TO_RECHECK":
                to_recheck_count += 1
            elif sow.status == "TO_CHECK":
                to_check_count += 1

            # 1. Sprawdzanie konieczności wykonania badania USG (>= 30 dni od inseminacji)

            if sow.status == "TO_CHECK":
                sows_to_check_usg.append(sow)

            # 2. Analiza zapotrzebowania na szczepienia ochronne i grupowanie
            for plan_dict in plans:
                vacc_status = sow.get_vaccination_status(plan_dict, current_date=today)
                if vacc_status['should_display']:
                    group_key = f"{plan_dict['name']} (Termin: {vacc_status['target_date'].strftime('%d.%m.%Y')})"
                    vaccination_groups[group_key].append({
                        'sow_id': sow.id,
                        'ear_tag': sow.ear_tag,
                        'status_display': sow.dynamic_status_display,  # Używamy nowej właściwości
                        'cycle_id': vacc_status['cycle_id'],
                        'vaccine_name': plan_dict['name'],
                        'is_eligible': vacc_status['is_eligible']
                    })

        return {
            'total_sows': len(sows),
            'inseminated_count': inseminated_count,
            'pregnant_count': pregnant_count,
            'lactating_count': lactating_count,
            'idle_count': idle_count,
            'to_recheck_count': to_recheck_count,
            'sows_to_check_usg': sows_to_check_usg,
            'vaccination_groups': dict(vaccination_groups),
            'all_sows': sows,
        }