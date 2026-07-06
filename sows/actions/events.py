from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404

from sows.domain.sow_state_machine import SowStateMachine
from sows.models import SowEventModel, SowModel
from sows.services.sow_event_service import SowEventService
from sows.services.sow_repository import SowRepository


PREGNANCY_CHECK_RESULTS = {"TAK", "NIE", "?"}


@dataclass(frozen=True)
class DeletedSowEvent:
    sow_id: int
    model_label: str
    object_id: int
    object_repr: str


class SowEventActions:
    def __init__(
        self,
        farm,
        user=None,
        repository: SowRepository | None = None,
        event_service: SowEventService | None = None,
    ):
        self.farm = farm
        self.user = user
        self.repository = repository or SowRepository(farm=farm)
        self.event_service = event_service or SowEventService(
            farm=farm,
            repository=self.repository,
        )

    @transaction.atomic
    def create_event(
        self,
        *,
        sow,
        sow_status: str,
        data: dict,
        farrowing_decision: str | None = None,
    ):
        return self.event_service.create_event(
            sow=sow,
            sow_status=sow_status,
            data=data,
            farrowing_decision=farrowing_decision,
        )

    @transaction.atomic
    def bulk_create_pregnancy_checks(
        self,
        *,
        sows,
        results_by_sow_id: dict,
        event_date=None,
    ) -> list[SowEventModel]:
        event_date = event_date or date.today()
        events = []

        for sow in sows:
            result = self._selected_pregnancy_result(results_by_sow_id, sow.id)
            if result not in PREGNANCY_CHECK_RESULTS:
                continue

            db_sow = self.repository.get_sow_model_by_id(sow.id)
            events.append(self.repository.create_event(
                sow=db_sow,
                event_type=SowStateMachine.PREGNANCY_CHECK,
                event_date=event_date,
                details={"result": result},
            ))

        return events

    @transaction.atomic
    def bulk_create_vaccinations(
        self,
        *,
        sow_ids: list,
        vaccine_name: str,
        cycle_id: str,
        event_date=None,
    ) -> list[SowEventModel]:
        event_date = event_date or date.today()
        events = []

        for sow_id in sow_ids:
            sow = self.repository.get_sow_model_by_id(sow_id)
            events.append(self.repository.create_event(
                sow=sow,
                event_type=SowStateMachine.VACCINATION,
                event_date=event_date,
                details={
                    "vaccine_name": vaccine_name,
                    "cycle_id": cycle_id,
                },
            ))

        return events

    @transaction.atomic
    def bulk_create_events(self, rows) -> list[SowEventModel]:
        events = [
            SowEventModel(
                sow=self._get_row_sow(row.sow.id),
                event_type=row.event_type,
                event_date=row.event_date,
                details=row.details,
            )
            for row in rows
        ]
        return self.repository.bulk_create_events(events)

    @transaction.atomic
    def update_event(self, *, event_id: int, data: dict) -> SowEventModel:
        event = self._get_event(event_id, lock_for_update=True)
        event.event_type = data["event_type"]
        event.event_date = data["event_date"]
        event.details = self.event_service.build_details(data)
        event.save()
        return event

    @transaction.atomic
    def delete_event(self, event_id: int) -> DeletedSowEvent:
        event = self._get_event(event_id, lock_for_update=True)
        deleted_event = DeletedSowEvent(
            sow_id=event.sow_id,
            model_label=event._meta.label,
            object_id=event.pk,
            object_repr=str(event),
        )
        event.delete()
        return deleted_event

    @staticmethod
    def _selected_pregnancy_result(results_by_sow_id: dict, sow_id: int) -> str | None:
        result = results_by_sow_id.get(sow_id)
        if result is None:
            result = results_by_sow_id.get(str(sow_id))
        return result

    def _get_row_sow(self, sow_id: int) -> SowModel:
        queryset = SowModel.objects.all()
        if self.farm is not None:
            queryset = queryset.filter(farm=self.farm)
        try:
            return queryset.get(id=sow_id)
        except SowModel.DoesNotExist as error:
            raise Http404("Nie znaleziono maciory w bieżącym gospodarstwie.") from error

    def _get_event(self, event_id: int, *, lock_for_update: bool = False) -> SowEventModel:
        queryset = SowEventModel.objects.select_related("sow")
        if lock_for_update:
            queryset = queryset.select_for_update()
        filters = {"id": event_id}
        if self.farm is not None:
            filters["sow__farm"] = self.farm
        return get_object_or_404(queryset, **filters)


def record_bulk_pregnancy_checks(
    *,
    farm,
    sows,
    results_by_sow_id: dict,
    event_date=None,
) -> list[SowEventModel]:
    return SowEventActions(farm=farm).bulk_create_pregnancy_checks(
        sows=sows,
        results_by_sow_id=results_by_sow_id,
        event_date=event_date,
    )


def record_bulk_vaccinations(
    *,
    farm,
    sow_ids: list,
    vaccine_name: str,
    cycle_id: str,
    event_date=None,
) -> list[SowEventModel]:
    return SowEventActions(farm=farm).bulk_create_vaccinations(
        sow_ids=sow_ids,
        vaccine_name=vaccine_name,
        cycle_id=cycle_id,
        event_date=event_date,
    )
