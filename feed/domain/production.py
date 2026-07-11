from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from feed.domain.exceptions import InvalidProductionTransitionError


@dataclass(frozen=True)
class ProductionCostResult:
    total_cost: Decimal
    cost_per_kg: Decimal
    is_partial: bool
    missing_components: tuple[str, ...]
    usage_count: int


def validate_completion_transition(*, current_status: str, completed_status: str, stage_one_status: str, skip_stages: bool) -> None:
    if current_status == completed_status:
        raise InvalidProductionTransitionError("To śrutowanie zostało już wcześniej zaksięgowane.")
    if not skip_stages and current_status != stage_one_status:
        raise InvalidProductionTransitionError("Nie można zakończyć produkcji przed wykonaniem Etapu 1.")


def completion_datetime_for(production_date, *, now=None):
    current = now or timezone.now()
    if timezone.is_aware(current):
        local_current = timezone.localtime(current)
        local_time = local_current.timetz().replace(tzinfo=None)
        return timezone.make_aware(
            datetime.combine(production_date, local_time),
            timezone.get_current_timezone(),
        )
    return datetime.combine(production_date, current.time())
