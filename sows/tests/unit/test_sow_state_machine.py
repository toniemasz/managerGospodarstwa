import pytest

from sows.domain.sow_state_machine import SowStateMachine


@pytest.mark.parametrize("status,event_type", [
    ('IDLE', 'INSEMINATION'),
    ('INSEMINATED', 'PREGNANCY_CHECK'),
    ('INSEMINATED', 'INSEMINATION'),
    ('TO_CHECK', 'PREGNANCY_CHECK'),
    ('TO_RECHECK', 'INSEMINATION'),
    ('PREGNANT', 'FARROWING'),
    ('LACTATING', 'WEANING'),
])
def test_state_machine_allows_valid_transitions(status, event_type):
    assert SowStateMachine.can_add_event(status, event_type) is True


@pytest.mark.parametrize("status,event_type", [
    ('IDLE', 'FARROWING'),
    ('LACTATING', 'INSEMINATION'),
    ('PREGNANT', 'WEANING'),
])
def test_state_machine_rejects_invalid_transitions(status, event_type):
    assert SowStateMachine.can_add_event(status, event_type) is False
    assert SowStateMachine.get_error_message(status)


@pytest.mark.parametrize("status", SowStateMachine.STATUSES)
def test_vaccination_is_allowed_in_every_state_and_does_not_change_main_status(status):
    assert SowStateMachine.can_add_event(status, 'VACCINATION') is True
    assert SowStateMachine.changes_main_status('VACCINATION') is False


@pytest.mark.parametrize("status", ['INSEMINATED', 'TO_CHECK', 'TO_RECHECK'])
def test_farrowing_without_positive_check_requires_confirmation(status):
    assert SowStateMachine.requires_confirmation(status, 'FARROWING') is True
    assert "nie ma zapisanego badania" in SowStateMachine.get_confirmation_message(status, 'FARROWING')


def test_confirmed_pregnant_farrowing_does_not_require_confirmation():
    assert SowStateMachine.requires_confirmation('PREGNANT', 'FARROWING') is False
