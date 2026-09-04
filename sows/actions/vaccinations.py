from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from common.cache import invalidate_farm_cache_on_commit
from sows.models import (
    SowEventModel,
    SowModel,
    VaccinationCycleModel,
    VaccinationPlanModel,
)
from sows.services.sow_repository import SowRepository
from sows.services.vaccination_schedule import VaccinationScheduleService


class VaccinationActionError(ValidationError):
    pass


class VaccinationPlanNameConflictError(ValidationError):
    pass


@dataclass(frozen=True)
class VaccinationCycleSelection:
    """Jednoznacznie wskazuje bieżący cykl szczepienia konkretnej maciory."""

    plan_id: int
    sow_id: int
    cycle_id: str
    scheduled_date: date


@transaction.atomic
def save_vaccination_plan(*, farm, form) -> VaccinationPlanModel:
    """Zapisuje plan po ponownym sprawdzeniu nazwy pod blokadą gospodarstwa."""

    farm.__class__.objects.select_for_update().get(pk=farm.pk)
    plan = form.save(commit=False)
    is_new = plan.pk is None
    plan.farm = farm
    plan.name = plan.name.strip()
    if VaccinationPlanModel.objects.filter(
        farm=farm,
        name__iexact=plan.name,
    ).exclude(pk=plan.pk).exists():
        raise VaccinationPlanNameConflictError(
            "Taki plan szczepień istnieje już w tym gospodarstwie."
        )
    if is_new:
        plan.starts_on = timezone.localdate()
    plan.save()
    form.save_m2m()
    return plan


class VaccinationActions:
    """Atomowe operacje zamykające cykle i zmieniające zakres planu."""

    def __init__(self, farm, user=None):
        if farm is None:
            raise ValueError("Operacje szczepień wymagają jawnego gospodarstwa.")
        self.farm = farm
        self.user = user

    @transaction.atomic
    def record_many(
        self,
        *,
        plan_id: int,
        sow_ids: list,
        cycle_id: str,
        scheduled_date: date,
        performed_date: date | None = None,
        note: str = "",
    ) -> list[SowEventModel]:
        selections = [
            VaccinationCycleSelection(
                plan_id=plan_id,
                sow_id=sow_id,
                cycle_id=cycle_id,
                scheduled_date=scheduled_date,
            )
            for sow_id in sow_ids
        ]
        return self.record_selected_cycles(
            selections=selections,
            performed_date=performed_date,
            note=note,
        )

    @transaction.atomic
    def record_selected_cycles(
        self,
        *,
        selections: list[VaccinationCycleSelection],
        performed_date: date | None = None,
        note: str = "",
    ) -> list[SowEventModel]:
        """Atomowo zapisuje wskazane, ponownie zweryfikowane cykle szczepień."""
        plan_sow_pairs = [
            (selection.plan_id, selection.sow_id)
            for selection in selections
        ]
        if len(plan_sow_pairs) != len(set(plan_sow_pairs)):
            raise VaccinationActionError(
                "Wybrano więcej niż jeden cykl tego samego planu dla jednej maciory. "
                "Odśwież ekran i spróbuj ponownie."
            )
        performed_date = performed_date or timezone.localdate()
        events = [
            self._record_one(
                plan_id=selection.plan_id,
                sow_id=selection.sow_id,
                cycle_id=selection.cycle_id,
                scheduled_date=selection.scheduled_date,
                performed_date=performed_date,
                note=note,
            )
            for selection in selections
        ]
        if events:
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return events

    def _record_one(
        self,
        *,
        plan_id: int,
        sow_id,
        cycle_id: str,
        scheduled_date: date,
        performed_date: date,
        note: str,
    ) -> SowEventModel:
        plan, sow = self._locked_plan_and_sow(plan_id, sow_id)
        self._validate_current_cycle(plan, sow, cycle_id, scheduled_date)
        self._create_cycle(
            plan=plan,
            sow=sow,
            cycle_id=cycle_id,
            scheduled_date=scheduled_date,
            status=VaccinationCycleModel.STATUS_COMPLETED,
            completed_at=performed_date,
            note=note,
        )
        details = {
            "vaccination_plan_id": plan.id,
            "vaccine_name": plan.name,
            "cycle_id": cycle_id,
            "scheduled_date": scheduled_date.isoformat(),
        }
        if note:
            details["note"] = note
        return SowEventModel.objects.create(
            sow=sow,
            event_type="VACCINATION",
            event_date=performed_date,
            details=details,
            vaccination_plan=plan,
            vaccine_name=plan.name,
            cycle_id=cycle_id,
            scheduled_date=scheduled_date,
        )

    @transaction.atomic
    def skip_cycle(
        self,
        *,
        plan_id: int,
        sow_id: int,
        cycle_id: str,
        scheduled_date: date,
        skipped_date: date | None = None,
        note: str = "",
    ) -> VaccinationCycleModel:
        plan, sow = self._locked_plan_and_sow(plan_id, sow_id)
        self._validate_current_cycle(plan, sow, cycle_id, scheduled_date)
        state = self._create_cycle(
            plan=plan,
            sow=sow,
            cycle_id=cycle_id,
            scheduled_date=scheduled_date,
            status=VaccinationCycleModel.STATUS_SKIPPED,
            skipped_at=skipped_date or timezone.localdate(),
            note=note,
        )
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return state

    @transaction.atomic
    def exclude_sow(self, *, plan_id: int, sow_id: int) -> VaccinationPlanModel:
        plan, sow = self._locked_plan_and_sow(plan_id, sow_id)
        if plan.scope == VaccinationPlanModel.SCOPE_SELECTED:
            plan.selected_sows.remove(sow)
        else:
            plan.excluded_sows.add(sow)
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return plan

    @transaction.atomic
    def deactivate_plan(self, *, plan_id: int) -> VaccinationPlanModel:
        plan = get_object_or_404(
            VaccinationPlanModel.objects.select_for_update(),
            id=plan_id,
            farm=self.farm,
        )
        if plan.is_active:
            plan.is_active = False
            plan.requires_configuration = False
            plan.save(update_fields=("is_active", "requires_configuration"))
            plan.selected_sows.clear()
            plan.excluded_sows.clear()
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return plan

    @transaction.atomic
    def reactivate_plan(self, *, plan_id: int) -> VaccinationPlanModel:
        """Włącza plan ponownie, wymagając odtworzenia utraconego wyboru macior."""
        plan = get_object_or_404(
            VaccinationPlanModel.objects.select_for_update(),
            id=plan_id,
            farm=self.farm,
        )
        if not plan.is_active:
            plan.is_active = True
            plan.requires_configuration = (
                plan.scope == VaccinationPlanModel.SCOPE_SELECTED
            )
            plan.save(update_fields=("is_active", "requires_configuration"))
            invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return plan

    def _locked_plan_and_sow(self, plan_id: int, sow_id) -> tuple[VaccinationPlanModel, SowModel]:
        plan = get_object_or_404(
            VaccinationPlanModel.objects.select_for_update(),
            id=plan_id,
            farm=self.farm,
            is_active=True,
            requires_configuration=False,
        )
        sow = get_object_or_404(
            SowModel.objects.select_for_update(),
            id=sow_id,
            farm=self.farm,
            is_archived=False,
        )
        return plan, sow

    def _validate_current_cycle(self, plan, sow, cycle_id: str, scheduled_date: date) -> None:
        sow_entity = SowRepository(self.farm).get_sow_by_id(sow.id)
        reminder = VaccinationScheduleService(self.farm).current_reminder(
            sow=sow_entity,
            plan_id=plan.id,
            current_date=timezone.localdate(),
        )
        if not reminder:
            raise VaccinationActionError("Ten cykl nie jest już aktywny dla tej maciory.")
        if reminder["cycle_id"] != cycle_id or reminder["scheduled_date"] != scheduled_date:
            raise VaccinationActionError("Dane cyklu są nieaktualne. Odśwież listę przypomnień.")

    @staticmethod
    def _create_cycle(**values) -> VaccinationCycleModel:
        try:
            return VaccinationCycleModel.objects.create(**values)
        except IntegrityError as error:
            raise VaccinationActionError("Ten cykl został już zamknięty.") from error
