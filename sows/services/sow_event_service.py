from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction

from farms.services.settings_service import get_farm_settings
from sows.domain.sow_state_machine import SowStateMachine
from sows.services.sow_repository import SowRepository


FARROWING_DECISION_WITHOUT_CHECK = 'without_check'
FARROWING_DECISION_AUTO_CHECK = 'auto_check'
FARROWING_DECISION_CANCEL = 'cancel'


@dataclass
class SowEventCreationResult:
    confirmation_required: bool = False
    cancelled: bool = False
    created_events: list = field(default_factory=list)
    message: str = ''

    @property
    def created_event(self):
        return self.created_events[-1] if self.created_events else None


class SowEventService:
    def __init__(self, farm=None, repository: SowRepository | None = None):
        self.farm = farm
        self.repository = repository or SowRepository(farm=farm)
        self.settings = get_farm_settings(farm) if farm is not None else None

    def build_details(self, data: dict) -> dict:
        event_type = data.get('event_type')
        details_mapping = {
            SowStateMachine.INSEMINATION: {'technician': data.get('technician') or ""},
            SowStateMachine.PREGNANCY_CHECK: {'result': data.get('pregnancy_result') or ""},
            SowStateMachine.FARROWING: {
                'born_alive': data.get('born_alive') or 0,
                'born_dead': data.get('born_dead') or 0,
            },
            SowStateMachine.WEANING: {'count': data.get('count') or 0},
            SowStateMachine.VACCINATION: {'vaccine_name': data.get('vaccine_name') or ""},
        }
        return details_mapping.get(event_type, {})

    def needs_farrowing_confirmation(self, sow_status: str, data: dict) -> bool:
        event_type = data.get('event_type')
        event_date = data.get('event_date')
        sow = data.get('sow')
        if not SowStateMachine.requires_confirmation(sow_status, event_type):
            return False
        if sow is None or event_date is None:
            return True
        return not self.repository.has_positive_pregnancy_check_before(sow.id, event_date)

    def create_event(
        self,
        *,
        sow,
        sow_status: str,
        data: dict,
        farrowing_decision: str | None = None,
    ) -> SowEventCreationResult:
        data = {**data, 'sow': sow}
        event_type = data.get('event_type')

        if self.needs_farrowing_confirmation(sow_status, data):
            if self.settings and not self.settings.allow_farrowing_without_pregnancy_check:
                raise ValidationError(
                    "Ustawienia gospodarstwa nie pozwalają dodać oproszenia bez wcześniejszego badania TAK."
                )
            if farrowing_decision in (None, ''):
                return SowEventCreationResult(
                    confirmation_required=True,
                    message=SowStateMachine.get_confirmation_message(sow_status, event_type),
                )
            if farrowing_decision == FARROWING_DECISION_CANCEL:
                return SowEventCreationResult(cancelled=True)
            if farrowing_decision == FARROWING_DECISION_WITHOUT_CHECK:
                return self._create_farrowing_without_check(sow=sow, data=data)
            if farrowing_decision == FARROWING_DECISION_AUTO_CHECK:
                return self._create_auto_check_and_farrowing(sow=sow, data=data)
            raise ValidationError("Nieznana decyzja potwierdzenia oproszenia.")

        if not SowStateMachine.can_add_event(sow_status, event_type):
            raise ValidationError(SowStateMachine.get_error_message(sow_status))

        event = self.repository.create_event(
            sow=sow,
            event_type=event_type,
            event_date=data.get('event_date'),
            details=self.build_details(data),
        )
        return SowEventCreationResult(created_events=[event])

    @transaction.atomic
    def _create_farrowing_without_check(self, *, sow, data: dict) -> SowEventCreationResult:
        details = self.build_details(data)
        details.update({
            'pregnancy_confirmation_missing': True,
            'pregnancy_confirmed_by': 'FARROWING',
        })
        event = self.repository.create_event(
            sow=sow,
            event_type=SowStateMachine.FARROWING,
            event_date=data.get('event_date'),
            details=details,
        )
        return SowEventCreationResult(created_events=[event])

    @transaction.atomic
    def _create_auto_check_and_farrowing(self, *, sow, data: dict) -> SowEventCreationResult:
        farrowing_date = data.get('event_date')
        check_date = farrowing_date
        if sow.entry_date is None or farrowing_date - timedelta(days=1) >= sow.entry_date:
            check_date = farrowing_date - timedelta(days=1)

        check = self.repository.create_event(
            sow=sow,
            event_type=SowStateMachine.PREGNANCY_CHECK,
            event_date=check_date,
            details={
                'result': 'TAK',
                'auto_generated': True,
                'generated_reason': 'FARROWING_WITHOUT_PRIOR_PREGNANCY_CHECK',
            },
        )
        farrowing = self.repository.create_event(
            sow=sow,
            event_type=SowStateMachine.FARROWING,
            event_date=farrowing_date,
            details=self.build_details(data),
        )
        return SowEventCreationResult(created_events=[check, farrowing])
