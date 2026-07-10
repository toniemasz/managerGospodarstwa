from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction

from sows.actions.events import SowEventActions
from sows.domain.sow_state_machine import SowStateMachine
from sows.services.sow_lifecycle import SowEvent
from sows.services.sow_repository import SowRepository


@dataclass
class BulkEventRow:
    form_index: int
    sow: object
    event_type: str
    event_date: object
    details: dict


@dataclass
class BulkEventResult:
    is_valid: bool
    created_count: int = 0
    errors: dict[int, list[str]] = field(default_factory=dict)

    def add_error(self, index: int, message: str) -> None:
        self.errors.setdefault(index, []).append(message)
        self.is_valid = False


class BulkSowEventService:
    def __init__(self, farm=None, repository: SowRepository | None = None):
        self.farm = farm
        self.repository = repository or SowRepository(farm=farm)

    def build_rows_from_formset(self, formset) -> list[BulkEventRow]:
        rows = []
        for index, form in enumerate(formset.forms):
            if form.cleaned_data.get('DELETE') or not form.has_row_data():
                continue
            rows.append(BulkEventRow(
                form_index=index,
                sow=form.cleaned_data['sow'],
                event_type=form.cleaned_data['event_type'],
                event_date=form.cleaned_data['event_date'],
                details=form.build_details(),
            ))
        return rows

    def validate_rows(self, rows: list[BulkEventRow]) -> BulkEventResult:
        result = BulkEventResult(is_valid=True)
        grouped_rows = defaultdict(list)
        for row in rows:
            grouped_rows[row.sow.id].append(row)

        for sow_id, sow_rows in grouped_rows.items():
            self._validate_input_order(sow_rows, result)
            if any(row.form_index in result.errors for row in sow_rows):
                continue

            sow_rows.sort(key=lambda row: row.form_index)
            sow = self.repository.get_sow_by_id(sow_id)
            pending_events = []

            for row in sow_rows:
                if self._would_insert_before_existing_production_event(sow, row):
                    result.add_error(
                        row.form_index,
                        "Data tego zdarzenia jest wcześniejsza niż istniejąca historia cyklu. Dodaj je pojedynczo po sprawdzeniu historii maciory.",
                    )
                    continue

                simulated_events = [
                    event for event in sow.all_events
                    if event.event_date <= row.event_date
                ] + pending_events
                simulated_sow = self.repository._map_to_sow(row.sow)
                simulated_sow.load_history(simulated_events)
                simulated_sow.update_state_for_date(row.event_date)

                if not self._is_event_allowed(simulated_sow.status, row.event_type):
                    result.add_error(row.form_index, SowStateMachine.get_error_message(simulated_sow.status))
                    continue

                pending_events.append(SowEvent(
                    event_type=row.event_type,
                    event_date=row.event_date,
                    details=row.details,
                ))

        return result

    @transaction.atomic
    def create_events(self, rows: list[BulkEventRow]) -> int:
        events = SowEventActions(
            farm=self.farm,
            repository=self.repository,
        ).bulk_create_events(rows)
        return len(events)

    @staticmethod
    def _validate_input_order(rows: list[BulkEventRow], result: BulkEventResult) -> None:
        previous_row = None
        for row in sorted(rows, key=lambda item: item.form_index):
            if previous_row and row.event_date < previous_row.event_date:
                result.add_error(
                    row.form_index,
                    "Zdarzenia dla tej samej maciory wpisz chronologicznie od góry do dołu: od najstarszego do najnowszego.",
                )
            previous_row = row

    @staticmethod
    def _is_event_allowed(status: str, event_type: str) -> bool:
        if SowStateMachine.requires_confirmation(status, event_type):
            return False
        return SowStateMachine.can_add_event(status, event_type)

    @staticmethod
    def _would_insert_before_existing_production_event(sow, row: BulkEventRow) -> bool:
        if row.event_type == 'VACCINATION':
            return False
        production_events = [
            event for event in sow.all_events
            if event.event_type != 'VACCINATION'
        ]
        if not production_events:
            return False
        latest_event_date = max(event.event_date for event in production_events)
        return row.event_date < latest_event_date
