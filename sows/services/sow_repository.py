from typing import List, Tuple

from django.shortcuts import get_object_or_404
from sows.models import SowEventModel, SowModel, VaccinationPlanModel
from farms.services.settings_service import get_farm_settings
from sows.domain.rules import GESTATION_DAYS
from sows.services.sow_lifecycle import Sow, SowEvent


class SowRepository:
    def __init__(self, farm):
        if farm is None:
            raise ValueError("Repozytorium macior wymaga jawnego gospodarstwa.")
        self.farm = farm
        self.gestation_days = GESTATION_DAYS
        settings = get_farm_settings(self.farm)
        self.gestation_days = settings.gestation_days

    def _filter_for_farm(self, **extra_filters):
        extra_filters['farm'] = self.farm
        return extra_filters

    def _map_to_sow(self, db_sow: SowModel) -> Sow:
        sow = Sow(
            id=db_sow.id,
            ear_tag=db_sow.ear_tag,
            entry_date=db_sow.entry_date,
            created_at=db_sow.created_at,
            is_archived=db_sow.is_archived,
            archive_reason=db_sow.archive_reason,
            death_date=db_sow.death_date,
            death_note=db_sow.death_note,
        )
        events = [
            SowEvent(
                event_type=e.event_type,
                event_date=e.event_date,
                details=e.details,
                id=e.id,
                created_at=e.created_at,
            )
            for e in db_sow.events.all()
        ]
        sow.load_history(events, gestation_days=self.gestation_days)
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

    def get_sow_model_by_id(self, sow_id: int) -> SowModel:
        return get_object_or_404(SowModel, **self._filter_for_farm(id=sow_id))

    def get_active_sow_models(self):
        return SowModel.objects.filter(**self._filter_for_farm(is_archived=False)).order_by('ear_tag')

    def has_positive_pregnancy_check_before(self, sow_id: int, event_date) -> bool:
        return SowEventModel.objects.filter(
            sow_id=sow_id,
            sow__farm=self.farm,
            event_type='PREGNANCY_CHECK',
            event_date__lte=event_date,
            details__result='TAK',
        ).exists()

    def create_event(self, sow, event_type: str, event_date, details: dict) -> SowEventModel:
        return SowEventModel.objects.create(
            sow=sow,
            event_type=event_type,
            event_date=event_date,
            details=details,
        )

    def bulk_create_events(self, events: list[SowEventModel]) -> list[SowEventModel]:
        return SowEventModel.objects.bulk_create(events)


class VaccinationPlanRepository:
    """Repozytorium do zarządzania regułami szczepień cyklicznych."""

    def __init__(self, farm):
        if farm is None:
            raise ValueError("Repozytorium szczepień wymaga jawnego gospodarstwa.")
        self.farm = farm

    def _filter_for_farm(self, **extra_filters):
        extra_filters['farm'] = self.farm
        return extra_filters

    def get_all_plans(self) -> List[VaccinationPlanModel]:
        return list(VaccinationPlanModel.objects.filter(**self._filter_for_farm()).order_by('name'))

    def get_plan_model_by_id(self, plan_id: int) -> VaccinationPlanModel:
        return get_object_or_404(VaccinationPlanModel, **self._filter_for_farm(id=plan_id))

    def get_plan_choices(self) -> List[Tuple[str, str]]:
        """Zwraca listę krotek (wartość, etykieta) do formularzy ChoiceField."""
        plans = VaccinationPlanModel.objects.filter(**self._filter_for_farm()).values_list('name', 'name').order_by('name')
        return [('', '--- Wybierz szczepienie cykliczne ---')] + list(plans)
