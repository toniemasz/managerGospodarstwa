from datetime import date, timedelta
import pytest
from sows.domain.entities import Sow, SowEvent

def test_should_calculate_expected_farrowing_date():
    sow = Sow(sow_id="PL-123", ear_tag="1", birth_date=date(2025, 1, 1))
    events = [SowEvent(event_type="INSEMINATION", event_date=date(2026, 5, 25), details={"technician": "Jan"})]
    sow.load_history(events)
    expected_farrowing = date(2026, 5, 25) + timedelta(days=114)
    assert sow.status == "INSEMINATED"
    assert sow.expected_farrowing_date == expected_farrowing

def test_should_change_status_to_idle_after_weaning():
    sow = Sow(sow_id="PL-123", ear_tag="1", birth_date=date(2025, 1, 1))
    events = [
        SowEvent(event_type="FARROWING", event_date=date(2026, 4, 25), details={"born_alive": 10, "born_dead": 0}),
        SowEvent(event_type="WEANING", event_date=date(2026, 5, 25), details={"count": 10})
    ]
    sow.load_history(events)
    assert sow.status == "IDLE"

def test_should_trigger_vaccination_alert_three_weeks_before_farrowing():
    sow = Sow(sow_id="PL-VACC", ear_tag="2", birth_date=date(2025, 1, 1))
    events = [SowEvent(event_type="INSEMINATION", event_date=date(2026, 5, 1), details={"technician": "Jan"})]
    sow.load_history(events)
    current_date_alert = sow.expected_farrowing_date - timedelta(days=21)
    assert sow.needs_vaccination(current_date=current_date_alert) is True



def test_should_initialize_sow_with_correct_defaults():
    sow = Sow(sow_id="PL-NEW-1", ear_tag="1234", birth_date=date(2025, 5, 1))

    assert sow.sow_id == "PL-NEW-1"
    assert sow.ear_tag == "1234"
    assert sow.birth_date == date(2025, 5, 1)
    assert sow.status == "IDLE"
