from sows.domain.event_details import build_event_details
from sows.domain.sow_state_machine import SowStateMachine
from sows.services.sow_repository import VaccinationPlanRepository


def build_event_details_for_farm(data: dict, *, farm) -> dict:
    """Buduje kanoniczne szczegóły zdarzenia i wiąże aktywny plan szczepienia."""

    details = build_event_details(data)
    if data.get("event_type") == SowStateMachine.VACCINATION and farm is not None:
        plan = VaccinationPlanRepository(farm).get_active_plan_by_name(
            details.get("vaccine_name", "")
        )
        if plan:
            details["vaccination_plan_id"] = plan.id
    return details
