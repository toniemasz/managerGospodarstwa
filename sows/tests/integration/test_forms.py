from datetime import date

import pytest

from sows.forms import SowEventForm, SowForm, VaccinationPlanForm
from sows.models import VaccinationPlanModel
from farms.services.farm_service import get_or_create_legacy_farm


@pytest.mark.django_db
def test_sow_form_accepts_basic_data():
    form = SowForm(data={'ear_tag': 'PL-1', 'entry_date': '2026-06-01'})

    assert form.is_valid() is True


@pytest.mark.django_db
def test_vaccination_plan_form_requires_exactly_one_trigger():
    no_trigger = VaccinationPlanForm(data={'name': 'Pusta', 'reminder_days_ahead': 7})
    many_triggers = VaccinationPlanForm(data={
        'name': 'Za dużo',
        'days_before_farrowing': 21,
        'interval_months': 4,
        'reminder_days_ahead': 7,
    })
    missing_source = VaccinationPlanForm(data={
        'name': 'Po zdarzeniu',
        'days_after_event': 14,
        'reminder_days_ahead': 7,
    })
    valid = VaccinationPlanForm(data={
        'name': 'Cykliczna',
        'interval_months': 4,
        'reminder_days_ahead': 7,
    })

    assert no_trigger.is_valid() is False
    assert many_triggers.is_valid() is False
    assert missing_source.is_valid() is False
    assert 'event_source' in missing_source.errors
    assert valid.is_valid() is True


@pytest.mark.django_db
@pytest.mark.parametrize("event_type, extra, expected_details", [
    ('INSEMINATION', {'technician': 'Jan'}, {'technician': 'Jan'}),
    ('PREGNANCY_CHECK', {'pregnancy_result': 'TAK'}, {'result': 'TAK'}),
    ('FARROWING', {'born_alive': 10, 'born_dead': 1}, {'born_alive': 10, 'born_dead': 1}),
    ('WEANING', {'count': 9}, {'count': 9}),
])
def test_sow_event_form_builds_details(event_type, extra, expected_details):
    farm = get_or_create_legacy_farm()
    data = {'event_type': event_type, 'event_date': date.today(), **extra}

    form = SowEventForm(data=data, farm=farm)

    assert form.is_valid() is True
    assert form.save(commit=False).details == expected_details


@pytest.mark.django_db
def test_sow_event_form_validates_vaccination_name_and_state_machine():
    farm = get_or_create_legacy_farm()
    VaccinationPlanModel.objects.create(farm=farm, name="Parwo", days_before_farrowing=21)

    missing_vaccine = SowEventForm(data={
        'event_type': 'VACCINATION',
        'event_date': date.today(),
    }, farm=farm)
    valid_vaccine = SowEventForm(data={
        'event_type': 'VACCINATION',
        'event_date': date.today(),
        'vaccine_name': 'Parwo',
    }, farm=farm)
    invalid_cycle_step = SowEventForm(
        data={'event_type': 'INSEMINATION', 'event_date': date.today()},
        sow_status='LACTATING',
        farm=farm,
    )

    assert missing_vaccine.is_valid() is False
    assert 'vaccine_name' in missing_vaccine.errors
    assert valid_vaccine.is_valid() is True
    assert invalid_cycle_step.is_valid() is False
    assert 'event_type' in invalid_cycle_step.errors
