from typing import List, Tuple

from django.db.models import Q
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
                vaccination_plan_id=e.vaccination_plan_id,
                vaccine_name=e.vaccine_name,
                cycle_id=e.cycle_id,
                scheduled_date=e.scheduled_date,
            )
            for e in db_sow.events.all()
        ]
        sow.load_history(events, gestation_days=self.gestation_days)
        transfer_events = []
        recorded_pre_weaning_deaths = 0
        for db_event in db_sow.events.all():
            for transfer in db_event.outgoing_piglet_transfers.all():
                history_event = SowEvent(
                    event_type="PIGLET_TRANSFER_OUT",
                    event_date=transfer.transfer_date,
                    details={
                        "quantity": transfer.quantity,
                        "other_sow_id": transfer.target_farrowing.sow_id,
                        "other_sow_ear_tag": transfer.target_farrowing.sow.ear_tag,
                        "note": transfer.note,
                        "is_canceled": transfer.is_canceled,
                    },
                    id=None,
                    created_at=transfer.created_at,
                )
                history_event.is_piglet_transfer = True
                history_event.transfer_id = transfer.id
                transfer_events.append(history_event)
            for transfer in db_event.incoming_piglet_transfers.all():
                history_event = SowEvent(
                    event_type="PIGLET_TRANSFER_IN",
                    event_date=transfer.transfer_date,
                    details={
                        "quantity": transfer.quantity,
                        "other_sow_id": transfer.source_farrowing.sow_id,
                        "other_sow_ear_tag": transfer.source_farrowing.sow.ear_tag,
                        "note": transfer.note,
                        "is_canceled": transfer.is_canceled,
                    },
                    id=None,
                    created_at=transfer.created_at,
                )
                history_event.is_piglet_transfer = True
                history_event.transfer_id = transfer.id
                transfer_events.append(history_event)
            recorded_pre_weaning_deaths += sum(
                report.quantity for report in db_event.pre_weaning_mortality_reports.all()
            )
        sow.all_events.extend(transfer_events)
        sow.all_events.sort(
            key=lambda event: (event.event_date, event.created_at or db_sow.created_at),
            reverse=True,
        )
        sow.recorded_pre_weaning_deaths = recorded_pre_weaning_deaths
        return sow

    def _sows_with_history(self):
        return SowModel.objects.prefetch_related(
            'events__outgoing_piglet_transfers__target_farrowing__sow',
            'events__incoming_piglet_transfers__source_farrowing__sow',
            'events__pre_weaning_mortality_reports',
        )

    def get_all_sows(self) -> list[Sow]:
        filters = self._filter_for_farm(is_archived=False)
        db_sows = self._sows_with_history().filter(**filters).order_by('ear_tag')
        return [self._map_to_sow(db_sow) for db_sow in db_sows]

    def get_archived_sows(self) -> list[Sow]:
        filters = self._filter_for_farm(is_archived=True)
        db_sows = self._sows_with_history().filter(**filters).order_by('ear_tag')
        return [self._map_to_sow(db_sow) for db_sow in db_sows]

    def get_sows_for_statistics(self) -> list[Sow]:
        """Zwraca aktywne i historyczne maciory dla raportów okresowych."""
        db_sows = self._sows_with_history().filter(
            farm=self.farm,
        ).order_by("ear_tag")
        return [self._map_to_sow(db_sow) for db_sow in db_sows]

    def get_sow_by_id(self, sow_id: int) -> Sow:
        filters = self._filter_for_farm(id=sow_id)
        db_sow = get_object_or_404(self._sows_with_history(), **filters)
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
        vaccination_fields = {}
        if event_type == 'VACCINATION':
            vaccination_fields = {
                'vaccine_name': details.get('vaccine_name') or '',
                'cycle_id': details.get('cycle_id') or '',
                'scheduled_date': details.get('scheduled_date') or None,
                'vaccination_plan_id': details.get('vaccination_plan_id') or None,
            }
        return SowEventModel.objects.create(
            sow=sow,
            event_type=event_type,
            event_date=event_date,
            details=details,
            **vaccination_fields,
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
        return list(
            VaccinationPlanModel.objects.filter(**self._filter_for_farm())
            .filter(Q(is_active=True) | Q(requires_configuration=True))
            .prefetch_related('selected_sows', 'excluded_sows')
            .order_by('name')
        )

    def get_plan_model_by_id(self, plan_id: int) -> VaccinationPlanModel:
        return get_object_or_404(
            VaccinationPlanModel.objects.filter(Q(is_active=True) | Q(requires_configuration=True)),
            **self._filter_for_farm(id=plan_id),
        )

    def get_plan_choices(self) -> List[Tuple[str, str]]:
        """Zwraca listę krotek (wartość, etykieta) do formularzy ChoiceField."""
        plans = VaccinationPlanModel.objects.filter(
            **self._filter_for_farm(is_active=True, requires_configuration=False)
        ).values_list('name', 'name').order_by('name')
        return [('', '--- Wybierz szczepienie cykliczne ---')] + list(plans)

    def get_active_plan_by_name(self, name: str) -> VaccinationPlanModel | None:
        return VaccinationPlanModel.objects.filter(
            farm=self.farm,
            name=name,
            is_active=True,
            requires_configuration=False,
        ).first()
