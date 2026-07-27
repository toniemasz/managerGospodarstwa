from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404

from common.cache import invalidate_farm_cache_on_commit
from sows.domain.sow_state_machine import SowStateMachine
from sows.models import SowEventModel, SowModel, VaccinationCycleModel
from sows.services.sow_event_service import SowEventService
from sows.services.piglet_care import PigletCareError, PigletCareService
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
        if farm is None:
            raise ValueError("Operacje zdarzeń macior wymagają jawnego gospodarstwa.")
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
        data = dict(data)
        if data.get("event_type") == SowStateMachine.WEANING:
            balance = PigletCareService(self.farm).validate_weaning(
                sow=sow,
                weaning_date=data["event_date"],
                quantity=data.get("count") or 0,
                lock_for_update=True,
            )
            self._add_weaning_balance_snapshot(data, balance)
        result = self.event_service.create_event(
            sow=sow,
            sow_status=sow_status,
            data=data,
            farrowing_decision=farrowing_decision,
        )
        if result.created_events:
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return result

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

        if events:
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return events

    @transaction.atomic
    def bulk_create_vaccinations(
        self,
        *,
        sow_ids: list,
        vaccine_name: str,
        cycle_id: str,
        event_date=None,
        note: str = "",
        plan_id: int | None = None,
        scheduled_date=None,
    ) -> list[SowEventModel]:
        if plan_id is not None:
            if scheduled_date is None:
                raise ValueError("Planowany termin jest wymagany dla cyklu planu szczepienia.")
            from sows.actions.vaccinations import VaccinationActions

            return VaccinationActions(self.farm, user=self.user).record_many(
                plan_id=plan_id,
                sow_ids=sow_ids,
                cycle_id=cycle_id,
                scheduled_date=scheduled_date,
                performed_date=event_date,
                note=note,
            )
        event_date = event_date or date.today()
        events = []
        details = {
            "vaccine_name": vaccine_name,
            "cycle_id": cycle_id,
        }
        if note:
            details["note"] = note

        for sow_id in sow_ids:
            sow = self.repository.get_sow_model_by_id(sow_id)
            events.append(self.repository.create_event(
                sow=sow,
                event_type=SowStateMachine.VACCINATION,
                event_date=event_date,
                details=details.copy(),
            ))

        if events:
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return events

    @transaction.atomic
    def bulk_create_events(self, rows) -> list[SowEventModel]:
        created_events = []
        care = PigletCareService(self.farm)
        for row in rows:
            sow = self._get_row_sow(row.sow.id)
            if row.event_type == SowStateMachine.WEANING:
                balance = care.validate_weaning(
                    sow=sow,
                    weaning_date=row.event_date,
                    quantity=int(row.details.get("count") or 0),
                    lock_for_update=True,
                )
                self._add_weaning_balance_snapshot(row.details, balance)
                row.details = self.event_service.build_details({
                    **row.details,
                    "event_type": row.event_type,
                })
            created_events.append(self.repository.create_event(
                sow=sow,
                event_type=row.event_type,
                event_date=row.event_date,
                details=row.details,
            ))
        if created_events:
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return created_events

    @transaction.atomic
    def update_event(self, *, event_id: int, data: dict) -> SowEventModel:
        event = self._get_event(event_id, lock_for_update=True)
        data = dict(data)
        care = PigletCareService(self.farm)
        if event.event_type == SowStateMachine.FARROWING:
            has_care_history = (
                event.outgoing_piglet_transfers.exists()
                or event.incoming_piglet_transfers.exists()
                or event.pre_weaning_mortality_reports.exists()
                or care.weanings_for_cycle(event).exists()
            )
            if has_care_history and (
                data["event_type"] != SowStateMachine.FARROWING
                or data["event_date"] != event.event_date
            ):
                raise PigletCareError(
                    "Nie można zmienić typu ani daty oproszenia powiązanego z odchowem. "
                    "Najpierw skoryguj późniejsze operacje."
                )
            if data["event_type"] == SowStateMachine.FARROWING:
                care.validate_cycle_history(
                    event,
                    born_alive_override=int(data.get("born_alive") or 0),
                )
        if data["event_type"] == SowStateMachine.WEANING:
            balance = PigletCareService(self.farm).validate_weaning(
                sow=event.sow,
                weaning_date=data["event_date"],
                quantity=data.get("count") or 0,
                replaced_weaning=event if event.event_type == SowStateMachine.WEANING else None,
                lock_for_update=True,
            )
            self._add_weaning_balance_snapshot(data, balance)
        old_plan_id = event.vaccination_plan_id
        old_cycle_id = event.cycle_id
        old_scheduled_date = event.scheduled_date
        event.event_type = data["event_type"]
        event.event_date = data["event_date"]
        event.details = self.event_service.build_details(data)
        if event.event_type == SowStateMachine.VACCINATION:
            event.vaccination_plan_id = event.details.get("vaccination_plan_id") or None
            event.vaccine_name = event.details.get("vaccine_name", "")
            if old_cycle_id and old_scheduled_date and event.vaccination_plan_id == old_plan_id:
                event.cycle_id = old_cycle_id
                event.scheduled_date = old_scheduled_date
                event.details.update({
                    "cycle_id": old_cycle_id,
                    "scheduled_date": old_scheduled_date.isoformat(),
                })
                VaccinationCycleModel.objects.filter(
                    plan_id=old_plan_id,
                    sow_id=event.sow_id,
                    cycle_id=old_cycle_id,
                    status=VaccinationCycleModel.STATUS_COMPLETED,
                ).update(completed_at=event.event_date)
            else:
                self._remove_completed_cycle(old_plan_id, event.sow_id, old_cycle_id)
                event.cycle_id = ""
                event.scheduled_date = None
        else:
            self._remove_completed_cycle(old_plan_id, event.sow_id, old_cycle_id)
            event.vaccination_plan = None
            event.vaccine_name = ""
            event.cycle_id = ""
            event.scheduled_date = None
        event.save()
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return event

    @transaction.atomic
    def delete_event(self, event_id: int) -> DeletedSowEvent:
        event = self._get_event(event_id, lock_for_update=True)
        if event.event_type == SowStateMachine.FARROWING:
            care = PigletCareService(self.farm)
            if (
                event.outgoing_piglet_transfers.exists()
                or event.incoming_piglet_transfers.exists()
                or event.pre_weaning_mortality_reports.exists()
                or care.weanings_for_cycle(event).exists()
            ):
                raise PigletCareError(
                    "Nie można usunąć oproszenia powiązanego z transferem, upadkiem lub odsadzeniem."
                )
        deleted_event = DeletedSowEvent(
            sow_id=event.sow_id,
            model_label=event._meta.label,
            object_id=event.pk,
            object_repr=str(event),
        )
        self._remove_completed_cycle(event.vaccination_plan_id, event.sow_id, event.cycle_id)
        event.delete()
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return deleted_event

    @staticmethod
    def _remove_completed_cycle(plan_id, sow_id, cycle_id) -> None:
        if not plan_id or not cycle_id:
            return
        VaccinationCycleModel.objects.filter(
            plan_id=plan_id,
            sow_id=sow_id,
            cycle_id=cycle_id,
            status=VaccinationCycleModel.STATUS_COMPLETED,
        ).delete()

    @staticmethod
    def _selected_pregnancy_result(results_by_sow_id: dict, sow_id: int) -> str | None:
        result = results_by_sow_id.get(sow_id)
        if result is None:
            result = results_by_sow_id.get(str(sow_id))
        return result

    def _get_row_sow(self, sow_id: int) -> SowModel:
        queryset = SowModel.objects.filter(farm=self.farm)
        try:
            return queryset.get(id=sow_id)
        except SowModel.DoesNotExist as error:
            raise Http404("Nie znaleziono maciory w bieżącym gospodarstwie.") from error

    def _get_event(self, event_id: int, *, lock_for_update: bool = False) -> SowEventModel:
        queryset = SowEventModel.objects.select_related("sow")
        if lock_for_update:
            queryset = queryset.select_for_update(of=("self",))
        filters = {"id": event_id, "sow__farm": self.farm}
        return get_object_or_404(queryset, **filters)

    @staticmethod
    def _add_weaning_balance_snapshot(data: dict, balance) -> None:
        quantity = int(data.get("count") or 0)
        difference = quantity - balance.available
        data["piglet_balance_expected"] = balance.available
        data["piglet_balance_difference"] = difference
        data["automatic_pre_weaning_deaths"] = max(-difference, 0)
        data["unrecorded_piglet_inflow"] = max(difference, 0)


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
    note: str = "",
    plan_id: int | None = None,
    scheduled_date=None,
) -> list[SowEventModel]:
    return SowEventActions(farm=farm).bulk_create_vaccinations(
        sow_ids=sow_ids,
        vaccine_name=vaccine_name,
        cycle_id=cycle_id,
        event_date=event_date,
        note=note,
        plan_id=plan_id,
        scheduled_date=scheduled_date,
    )
