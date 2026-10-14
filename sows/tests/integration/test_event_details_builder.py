from datetime import date

import pytest
from django.contrib.auth.models import User

from farms.services.farm_service import get_or_create_user_farm
from sows.forms import BulkSowEventFormSet
from sows.models import SowModel, VaccinationPlanModel
from sows.services.bulk_event_service import BulkSowEventService
from sows.services.event_details import build_event_details_for_farm
from sows.services.sow_event_service import SowEventService


@pytest.mark.django_db
def test_single_and_bulk_vaccination_use_the_same_farm_scoped_plan():
    user = User.objects.create_user(username="event-details")
    farm = get_or_create_user_farm(user)
    sow = SowModel.objects.create(
        farm=farm,
        ear_tag="DETAILS-1",
        entry_date=date(2026, 1, 1),
    )
    plan = VaccinationPlanModel.objects.create(farm=farm, name="Parwo")

    single_details = SowEventService(farm=farm).build_details({
        "event_type": "VACCINATION",
        "vaccine_name": "pArWo",
    })
    formset = BulkSowEventFormSet(
        data={
            "events-TOTAL_FORMS": "1",
            "events-INITIAL_FORMS": "0",
            "events-MIN_NUM_FORMS": "0",
            "events-MAX_NUM_FORMS": "1000",
            "events-0-sow_ear_tag": sow.ear_tag,
            "events-0-event_type": "VACCINATION",
            "events-0-event_date": "2026-06-01",
            "events-0-vaccine_name": plan.name,
        },
        prefix="events",
        form_kwargs={"farm": farm},
    )

    assert formset.is_valid(), formset.errors
    bulk_details = BulkSowEventService(farm=farm).build_rows_from_formset(formset)[0].details
    assert single_details["vaccination_plan_id"] == plan.pk
    assert bulk_details["vaccination_plan_id"] == plan.pk


@pytest.mark.django_db
def test_event_details_builder_does_not_link_missing_or_foreign_plan():
    owner = User.objects.create_user(username="event-owner")
    farm = get_or_create_user_farm(owner)
    other = User.objects.create_user(username="event-other")
    other_farm = get_or_create_user_farm(other)
    VaccinationPlanModel.objects.create(farm=other_farm, name="Tylko obcy plan")

    missing = build_event_details_for_farm(
        {"event_type": "VACCINATION", "vaccine_name": "Brak planu"},
        farm=farm,
    )
    foreign = build_event_details_for_farm(
        {"event_type": "VACCINATION", "vaccine_name": "TYLKO OBCY PLAN"},
        farm=farm,
    )

    assert "vaccination_plan_id" not in missing
    assert "vaccination_plan_id" not in foreign
