from typing import List, Tuple

from django.shortcuts import get_object_or_404
from sows.models import SowModel, VaccinationPlanModel
from sows.services.sow_lifecycle import Sow, SowEvent


class SowRepository:
    def __init__(self, farm=None):
        self.farm = farm

    def _filter_for_farm(self, **extra_filters):
        if self.farm is not None:
            extra_filters['farm'] = self.farm
        return extra_filters

    def _map_to_sow(self, db_sow: SowModel) -> Sow:
        sow = Sow(
            id=db_sow.id,
            ear_tag=db_sow.ear_tag,
            entry_date=db_sow.entry_date,
            created_at=db_sow.created_at,
            is_archived=db_sow.is_archived
        )
        events = [
            SowEvent(event_type=e.event_type, event_date=e.event_date, details=e.details, id=e.id)
            for e in db_sow.events.all()
        ]
        sow.load_history(events)
        return sow

    def get_all_sows(self) -> list[Sow]:
        filters = self._filter_for_farm(is_archived=False)
        db_sows = SowModel.objects.prefetch_related('events').filter(**filters).order_by('ear_tag')
        return [self._map_to_sow(db_sow) for db_sow in db_sows]

    def get_archived_sows(self) -> list[Sow]:
        filters = self._filter_for_farm(is_archived=True)
        db_sows = SowModel.objects.prefetch_related('events').filter(**filters).order_by('ear_tag')
        return [self._map_to_sow(db_sow) for db_sow in db_sows]

    def get_sow_by_id(self, sow_id: int) -> Sow:
        filters = self._filter_for_farm(id=sow_id)
        db_sow = get_object_or_404(SowModel.objects.prefetch_related('events'), **filters)
        return self._map_to_sow(db_sow)


class VaccinationPlanRepository:
    """Repozytorium do zarządzania regułami szczepień cyklicznych."""

    def __init__(self, farm=None):
        self.farm = farm

    def _filter_for_farm(self, **extra_filters):
        if self.farm is not None:
            extra_filters['farm'] = self.farm
        return extra_filters

    def get_all_plans(self) -> List[VaccinationPlanModel]:
        return list(VaccinationPlanModel.objects.filter(**self._filter_for_farm()).order_by('name'))

    def get_plan_choices(self) -> List[Tuple[str, str]]:
        """Zwraca listę krotek (wartość, etykieta) do formularzy ChoiceField."""
        plans = VaccinationPlanModel.objects.filter(**self._filter_for_farm()).values_list('name', 'name').order_by('name')
        return [('', '--- Wybierz szczepienie cykliczne ---')] + list(plans)
