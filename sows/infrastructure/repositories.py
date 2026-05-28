# sows/infrastructure/repositories.py
from django.shortcuts import get_object_or_404
from sows.models import SowModel
from sows.domain.entities import Sow, SowEvent

class SowRepository:
    def _map_to_domain(self, db_sow: SowModel) -> Sow:
        sow = Sow(id=db_sow.id, ear_tag=db_sow.ear_tag, entry_date=db_sow.entry_date, created_at=db_sow.created_at)
        events = [
            SowEvent(event_type=e.event_type, event_date=e.event_date, details=e.details, id=e.id)  # <--- dodaj id=e.id
            for e in db_sow.events.all()
        ]
        sow.load_history(events)
        return sow

    def get_all_sows(self) -> list[Sow]:
        db_sows = SowModel.objects.prefetch_related('events').all()
        return [self._map_to_domain(db_sow) for db_sow in db_sows]

    def get_sow_by_id(self, sow_id: int) -> Sow:
        db_sow = get_object_or_404(SowModel.objects.prefetch_related('events'), id=sow_id)
        return self._map_to_domain(db_sow)


from sows.models import VaccinationPlanModel
from typing import List, Tuple


class VaccinationPlanRepository:
    """Repozytorium do zarządzania regułami szczepień cyklicznych."""

    def get_all_plans(self) -> List[VaccinationPlanModel]:
        return list(VaccinationPlanModel.objects.all().order_by('name'))

    def get_plan_choices(self) -> List[Tuple[str, str]]:
        """Zwraca listę krotek (wartość, etykieta) do formularzy ChoiceField."""
        plans = VaccinationPlanModel.objects.values_list('name', 'name').order_by('name')
        return [('', '--- Wybierz szczepienie cykliczne ---')] + list(plans)