# sows/application/services.py
from datetime import date
from sows.infrastructure.repositories import SowRepository

class SowDashboardService:
    """Serwis przygotowujący pełne statystyki dla panelu głównego."""

    def __init__(self, repository: SowRepository = None):
        self.repository = repository or SowRepository()

    def get_dashboard_summary(self) -> dict:
        today = date.today()
        sows = self.repository.get_all_sows()

        sows_to_vaccinate = []
        inseminated_count = 0
        lactating_count = 0
        idle_count = 0

        for sow in sows:
            if sow.status == "INSEMINATED":
                inseminated_count += 1
            elif sow.status == "LACTATING":
                lactating_count += 1
            elif sow.status == "IDLE":
                idle_count += 1

            if sow.needs_vaccination(current_date=today):
                sows_to_vaccinate.append(sow)

        return {
            'total_sows': len(sows),
            'inseminated_count': inseminated_count,
            'lactating_count': lactating_count,
            'idle_count': idle_count,
            'sows_to_vaccinate': sows_to_vaccinate,
            'all_sows': sows,
        }