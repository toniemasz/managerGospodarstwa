from datetime import date

import pytest
from django.contrib.auth.models import User

from farms.services.farm_service import get_or_create_user_farm
from sows.forms import VaccinationPlanForm
from sows.models import SowModel, VaccinationPlanModel


@pytest.fixture
def farm(db):
    user = User.objects.create_user(
        username='vaccination-form-owner',
        password='password',
    )
    return get_or_create_user_farm(user)


def vaccination_plan_data(**overrides):
    data = {
        'name': 'Szczepienie testowe',
        'trigger_type': 'BEFORE_FARROWING',
        'days_before_farrowing': '21',
        'reminder_days_ahead': '7',
        'scope': VaccinationPlanModel.SCOPE_ALL,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_before_farrowing_plan_is_valid(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(),
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    plan = form.save()

    assert plan.farm == farm
    assert plan.days_before_farrowing == 21
    assert plan.days_after_event is None
    assert plan.event_source is None
    assert plan.interval_value is None
    assert plan.interval_unit is None
    assert plan.schedule_mode is None
    assert plan.first_due_date is None
    assert plan.is_active is True
    assert plan.requires_configuration is False


@pytest.mark.django_db
def test_before_farrowing_type_clears_fields_from_other_trigger_types(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            days_after_event='10',
            event_source='INSEMINATION',
            interval_value='4',
            interval_unit=VaccinationPlanModel.INTERVAL_MONTHS,
            schedule_mode=VaccinationPlanModel.SCHEDULE_FIXED,
            first_due_date='2026-07-12',
        ),
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    plan = form.save()

    assert plan.days_before_farrowing == 21
    assert plan.days_after_event is None
    assert plan.event_source is None
    assert plan.interval_value is None
    assert plan.interval_unit is None
    assert plan.interval_months is None
    assert plan.schedule_mode is None
    assert plan.first_due_date is None


@pytest.mark.django_db
def test_after_event_plan_is_valid(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            name='Po inseminacji',
            trigger_type='AFTER_EVENT',
            days_before_farrowing='',
            days_after_event='14',
            event_source='INSEMINATION',
        ),
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    plan = form.save()

    assert plan.days_before_farrowing is None
    assert plan.days_after_event == 14
    assert plan.event_source == 'INSEMINATION'
    assert plan.interval_value is None
    assert plan.interval_unit is None
    assert plan.schedule_mode is None
    assert plan.first_due_date is None


@pytest.mark.django_db
def test_after_event_plan_requires_event_source(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            trigger_type='AFTER_EVENT',
            days_before_farrowing='',
            days_after_event='14',
            event_source='',
        ),
        farm=farm,
    )

    assert form.is_valid() is False
    assert 'event_source' in form.errors


@pytest.mark.django_db
def test_after_event_plan_requires_number_of_days(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            trigger_type='AFTER_EVENT',
            days_before_farrowing='',
            days_after_event='',
            event_source='FARROWING',
        ),
        farm=farm,
    )

    assert form.is_valid() is False
    assert 'days_after_event' in form.errors


@pytest.mark.django_db
def test_interval_plan_is_valid_and_sets_legacy_interval_months(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            name='Cykliczne co cztery miesiące',
            trigger_type='INTERVAL',
            days_before_farrowing='',
            interval_value='4',
            interval_unit=VaccinationPlanModel.INTERVAL_MONTHS,
            schedule_mode=VaccinationPlanModel.SCHEDULE_FIXED,
            first_due_date='2026-07-12',
        ),
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    plan = form.save()

    assert plan.days_before_farrowing is None
    assert plan.days_after_event is None
    assert plan.event_source is None
    assert plan.interval_value == 4
    assert plan.interval_unit == VaccinationPlanModel.INTERVAL_MONTHS
    assert plan.interval_months == 4
    assert plan.schedule_mode == VaccinationPlanModel.SCHEDULE_FIXED
    assert plan.first_due_date == date(2026, 7, 12)


@pytest.mark.django_db
@pytest.mark.parametrize(
    'missing_field',
    [
        'interval_value',
        'interval_unit',
        'schedule_mode',
        'first_due_date',
    ],
)
def test_interval_plan_requires_complete_schedule(farm, missing_field):
    data = vaccination_plan_data(
        trigger_type='INTERVAL',
        days_before_farrowing='',
        interval_value='4',
        interval_unit=VaccinationPlanModel.INTERVAL_MONTHS,
        schedule_mode=VaccinationPlanModel.SCHEDULE_FIXED,
        first_due_date='2026-07-12',
    )
    data[missing_field] = ''

    form = VaccinationPlanForm(data=data, farm=farm)

    assert form.is_valid() is False
    assert missing_field in form.errors


@pytest.mark.django_db
def test_trigger_type_is_required(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            trigger_type='',
        ),
        farm=farm,
    )

    assert form.is_valid() is False
    assert 'trigger_type' in form.errors


@pytest.mark.django_db
def test_selected_scope_requires_at_least_one_sow(farm):
    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            scope=VaccinationPlanModel.SCOPE_SELECTED,
            selected_sows=[],
        ),
        farm=farm,
    )

    assert form.is_valid() is False
    assert 'selected_sows' in form.errors


@pytest.mark.django_db
def test_selected_scope_saves_selected_sows(farm):
    first_sow = SowModel.objects.create(
        farm=farm,
        ear_tag='SELECTED-001',
    )
    second_sow = SowModel.objects.create(
        farm=farm,
        ear_tag='SELECTED-002',
    )

    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            scope=VaccinationPlanModel.SCOPE_SELECTED,
            selected_sows=[
                str(first_sow.id),
                str(second_sow.id),
            ],
        ),
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    plan = form.save()

    assert set(plan.selected_sows.values_list('id', flat=True)) == {
        first_sow.id,
        second_sow.id,
    }


@pytest.mark.django_db
def test_all_scope_clears_previously_selected_sows(farm):
    sow = SowModel.objects.create(
        farm=farm,
        ear_tag='REMOVE-SELECTION',
    )
    plan = VaccinationPlanModel.objects.create(
        farm=farm,
        name='Plan wybranych macior',
        days_before_farrowing=14,
        reminder_days_ahead=7,
        scope=VaccinationPlanModel.SCOPE_SELECTED,
    )
    plan.selected_sows.add(sow)

    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            name=plan.name,
            days_before_farrowing='14',
            scope=VaccinationPlanModel.SCOPE_ALL,
        ),
        instance=plan,
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    updated_plan = form.save()

    assert updated_plan.scope == VaccinationPlanModel.SCOPE_ALL
    assert not updated_plan.selected_sows.exists()


@pytest.mark.django_db
def test_editing_interval_plan_to_before_farrowing_clears_interval(farm):
    plan = VaccinationPlanModel.objects.create(
        farm=farm,
        name='Plan do zmiany',
        interval_months=4,
        interval_value=4,
        interval_unit=VaccinationPlanModel.INTERVAL_MONTHS,
        schedule_mode=VaccinationPlanModel.SCHEDULE_FIXED,
        first_due_date=date(2026, 7, 12),
        reminder_days_ahead=7,
        scope=VaccinationPlanModel.SCOPE_ALL,
    )

    form = VaccinationPlanForm(
        data=vaccination_plan_data(
            name=plan.name,
            trigger_type='BEFORE_FARROWING',
            days_before_farrowing='21',
        ),
        instance=plan,
        farm=farm,
    )

    assert form.is_valid(), form.errors.as_json()

    updated_plan = form.save()
    updated_plan.refresh_from_db()

    assert updated_plan.days_before_farrowing == 21
    assert updated_plan.interval_value is None
    assert updated_plan.interval_unit is None
    assert updated_plan.interval_months is None
    assert updated_plan.schedule_mode is None
    assert updated_plan.first_due_date is None


@pytest.mark.django_db
def test_legacy_interval_months_plan_gets_interval_trigger_initial_data(farm):
    plan = VaccinationPlanModel.objects.create(
        farm=farm,
        name='Stary plan cykliczny',
        interval_months=4,
        interval_value=None,
        interval_unit=None,
        schedule_mode=None,
        first_due_date=None,
        reminder_days_ahead=7,
    )

    form = VaccinationPlanForm(
        instance=plan,
        farm=farm,
    )

    assert form.initial['trigger_type'] == 'INTERVAL'
    assert form.initial['interval_value'] == 4
    assert form.initial['interval_unit'] == VaccinationPlanModel.INTERVAL_MONTHS