from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User

from farms.services.farm_service import get_or_create_user_farm
from sows.models import SowEventModel, SowModel
from sows.services.sow_event_service import (
    FARROWING_DECISION_AUTO_CHECK,
    FARROWING_DECISION_CANCEL,
    FARROWING_DECISION_WITHOUT_CHECK,
    SowEventService,
)


@pytest.fixture
def sow_with_farm():
    user = User.objects.create_user(username='event-service-user')
    farm = get_or_create_user_farm(user)
    sow = SowModel.objects.create(ear_tag='EVENT-1', farm=farm, entry_date=date(2026, 1, 1))
    return sow, farm


def _data(event_type, **extra):
    return {
        'event_type': event_type,
        'event_date': extra.pop('event_date', date(2026, 6, 1)),
        **extra,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("status,event_type,extra,expected_details", [
    ('IDLE', 'INSEMINATION', {'technician': 'Jan'}, {'technician': 'Jan'}),
    ('INSEMINATED', 'PREGNANCY_CHECK', {'pregnancy_result': 'TAK'}, {'result': 'TAK'}),
    ('INSEMINATED', 'PREGNANCY_CHECK', {'pregnancy_result': 'NIE'}, {'result': 'NIE'}),
    ('TO_RECHECK', 'PREGNANCY_CHECK', {'pregnancy_result': '?'}, {'result': '?'}),
    ('PREGNANT', 'FARROWING', {'born_alive': 11, 'born_dead': 1}, {'born_alive': 11, 'born_dead': 1}),
    ('LACTATING', 'WEANING', {'count': 10}, {'count': 10}),
    ('IDLE', 'VACCINATION', {'vaccine_name': 'Parwo'}, {'vaccine_name': 'Parwo'}),
])
def test_single_event_service_creates_supported_events(sow_with_farm, status, event_type, extra, expected_details):
    sow, farm = sow_with_farm
    result = SowEventService(farm=farm).create_event(
        sow=sow,
        sow_status=status,
        data=_data(event_type, **extra),
    )

    assert result.created_event.event_type == event_type
    assert result.created_event.details == expected_details


@pytest.mark.django_db
def test_farrowing_without_check_first_requires_confirmation(sow_with_farm):
    sow, farm = sow_with_farm

    result = SowEventService(farm=farm).create_event(
        sow=sow,
        sow_status='INSEMINATED',
        data=_data('FARROWING', born_alive=10, born_dead=0),
    )

    assert result.confirmation_required is True
    assert SowEventModel.objects.filter(sow=sow).count() == 0


@pytest.mark.django_db
def test_farrowing_without_check_can_be_added_with_marker(sow_with_farm):
    sow, farm = sow_with_farm

    result = SowEventService(farm=farm).create_event(
        sow=sow,
        sow_status='TO_CHECK',
        data=_data('FARROWING', born_alive=10, born_dead=0),
        farrowing_decision=FARROWING_DECISION_WITHOUT_CHECK,
    )

    event = result.created_event
    assert event.event_type == 'FARROWING'
    assert event.details['pregnancy_confirmation_missing'] is True
    assert event.details['pregnancy_confirmed_by'] == 'FARROWING'
    assert SowEventModel.objects.filter(sow=sow).count() == 1


@pytest.mark.django_db
def test_farrowing_without_check_can_add_auto_positive_check_in_one_flow(sow_with_farm):
    sow, farm = sow_with_farm
    farrowing_date = date(2026, 6, 10)

    SowEventService(farm=farm).create_event(
        sow=sow,
        sow_status='TO_RECHECK',
        data=_data('FARROWING', event_date=farrowing_date, born_alive=12, born_dead=1),
        farrowing_decision=FARROWING_DECISION_AUTO_CHECK,
    )

    events = list(SowEventModel.objects.filter(sow=sow).order_by('event_date', 'id'))
    assert [event.event_type for event in events] == ['PREGNANCY_CHECK', 'FARROWING']
    assert events[0].event_date == farrowing_date - timedelta(days=1)
    assert events[0].details == {
        'result': 'TAK',
        'auto_generated': True,
        'generated_reason': 'FARROWING_WITHOUT_PRIOR_PREGNANCY_CHECK',
    }


@pytest.mark.django_db
def test_farrowing_without_check_cancel_does_not_save_anything(sow_with_farm):
    sow, farm = sow_with_farm

    result = SowEventService(farm=farm).create_event(
        sow=sow,
        sow_status='INSEMINATED',
        data=_data('FARROWING', born_alive=10, born_dead=0),
        farrowing_decision=FARROWING_DECISION_CANCEL,
    )

    assert result.cancelled is True
    assert SowEventModel.objects.filter(sow=sow).count() == 0
