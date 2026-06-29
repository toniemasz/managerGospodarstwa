from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError

from sows.domain.sow_state_machine import SowStateMachine


def _value(data: Mapping[str, Any], key: str, default: Any) -> Any:
    value = data.get(key)
    return default if value in (None, '') else value


def build_event_details(data: Mapping[str, Any]) -> dict:
    event_type = data.get('event_type')

    if event_type == SowStateMachine.INSEMINATION:
        return {'technician': _value(data, 'technician', '')}
    if event_type == SowStateMachine.PREGNANCY_CHECK:
        return {'result': _value(data, 'pregnancy_result', '')}
    if event_type == SowStateMachine.FARROWING:
        return {
            'born_alive': _value(data, 'born_alive', 0),
            'born_dead': _value(data, 'born_dead', 0),
        }
    if event_type == SowStateMachine.WEANING:
        return {'count': _value(data, 'count', 0)}
    if event_type == SowStateMachine.VACCINATION:
        return {'vaccine_name': _value(data, 'vaccine_name', '')}

    raise ValidationError("Nieznany typ zdarzenia. Wybierz poprawny typ z listy.")


def initial_data_from_event_details(event_type: str, details: Mapping[str, Any] | None) -> dict:
    details = details or {}

    if event_type == SowStateMachine.INSEMINATION:
        return {'technician': details.get('technician', '')}
    if event_type == SowStateMachine.PREGNANCY_CHECK:
        return {'pregnancy_result': details.get('result', '')}
    if event_type == SowStateMachine.FARROWING:
        return {
            'born_alive': details.get('born_alive', 0),
            'born_dead': details.get('born_dead', 0),
        }
    if event_type == SowStateMachine.WEANING:
        return {'count': details.get('count', 0)}
    if event_type == SowStateMachine.VACCINATION:
        return {'vaccine_name': details.get('vaccine_name', '')}

    raise ValidationError("Nieznany typ zdarzenia. Nie można odtworzyć danych formularza.")
