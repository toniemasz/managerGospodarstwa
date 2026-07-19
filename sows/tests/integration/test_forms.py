from datetime import date

import pytest

from sows.forms import SowEventForm, SowForm, VaccinationPlanForm
from sows.models import SowModel, VaccinationPlanModel
from farms.services.farm_service import get_or_create_legacy_farm, get_or_create_user_farm
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_sow_form_accepts_basic_data():
    form = SowForm(data={'ear_tag': 'PL-1', 'entry_date': '2026-06-01'})

    assert form.is_valid() is True


@pytest.mark.django_db
def test_sow_number_is_unique_only_for_active_sows_in_same_farm():
    farm = get_or_create_user_farm(User.objects.create_user(username='sow-unique'))
    other_farm = get_or_create_user_farm(User.objects.create_user(username='sow-unique-other'))
    SowModel.objects.create(farm=farm, ear_tag='ARCH-1', is_archived=True)
    SowModel.objects.create(farm=farm, ear_tag='ACTIVE-1')

    archived_reuse = SowForm(
        data={'ear_tag': ' arch-1 ', 'entry_date': '2026-07-01'},
        farm=farm,
    )
    active_duplicate = SowForm(
        data={'ear_tag': ' active-1 ', 'entry_date': '2026-07-01'},
        farm=farm,
    )
    other_farm_form = SowForm(
        data={'ear_tag': 'ACTIVE-1', 'entry_date': '2026-07-01'},
        farm=other_farm,
    )

    assert archived_reuse.is_valid() is True
    assert archived_reuse.cleaned_data['ear_tag'] == 'arch-1'
    assert active_duplicate.is_valid() is False
    assert 'ear_tag' in active_duplicate.errors
    assert other_farm_form.is_valid() is True


@pytest.mark.django_db
def test_vaccination_plan_form_requires_exactly_one_trigger():
    no_trigger = VaccinationPlanForm(data={'name': 'Pusta', 'reminder_days_ahead': 7})
    missing_source = VaccinationPlanForm(data={
        'name': 'Po zdarzeniu',
        'trigger_type': VaccinationPlanForm.TRIGGER_AFTER_EVENT,
        'days_after_event': 14,
        'reminder_days_ahead': 7,
    })
    valid = VaccinationPlanForm(data={
        'name': 'Cykliczna',
        'trigger_type': VaccinationPlanForm.TRIGGER_INTERVAL,
        'interval_value': 4,
        'interval_unit': 'MONTHS',
        'schedule_mode': 'FIXED',
        'first_due_date': '2026-07-01',
        'reminder_days_ahead': 7,
    })

    assert no_trigger.is_valid() is False
    assert missing_source.is_valid() is False
    assert 'event_source' in missing_source.errors
    assert valid.is_valid() is True


@pytest.mark.django_db
def test_periodic_vaccination_plan_requires_explicit_first_due_date():
    form = VaccinationPlanForm(data={
        'name': 'Bez daty',
        'trigger_type': VaccinationPlanForm.TRIGGER_INTERVAL,
        'interval_value': 2,
        'interval_unit': 'WEEKS',
        'schedule_mode': 'FIXED',
        'reminder_days_ahead': 7,
    })

    assert form.is_valid() is False
    assert 'first_due_date' in form.errors


@pytest.mark.django_db
def test_selected_scope_rejects_archived_and_foreign_sows():
    farm = get_or_create_user_farm(User.objects.create_user(username='form-scope'))
    other_farm = get_or_create_user_farm(User.objects.create_user(username='form-scope-other'))
    active = SowModel.objects.create(farm=farm, ear_tag='ACTIVE')
    archived = SowModel.objects.create(farm=farm, ear_tag='ARCHIVED', is_archived=True)
    foreign = SowModel.objects.create(farm=other_farm, ear_tag='FOREIGN')
    common = {
        'name': 'Zakres',
        'trigger_type': VaccinationPlanForm.TRIGGER_INTERVAL,
        'interval_value': 1,
        'interval_unit': 'YEARS',
        'schedule_mode': 'FIXED',
        'first_due_date': '2026-07-01',
        'scope': 'SELECTED',
        'reminder_days_ahead': 7,
    }

    valid = VaccinationPlanForm(data={**common, 'selected_sows': [active.id]}, farm=farm)
    archived_form = VaccinationPlanForm(data={**common, 'selected_sows': [archived.id]}, farm=farm)
    foreign_form = VaccinationPlanForm(data={**common, 'selected_sows': [foreign.id]}, farm=farm)

    assert valid.is_valid() is True
    assert archived_form.is_valid() is False
    assert foreign_form.is_valid() is False
    assert 'selected_sows' in archived_form.errors
    assert 'selected_sows' in foreign_form.errors


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
