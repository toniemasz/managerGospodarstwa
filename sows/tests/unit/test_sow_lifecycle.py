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


# sows/tests/unit/test_sow_lifecycle.py
from datetime import date, timedelta
from sows.domain.entities import Sow, SowEvent


def test_should_categorize_events_and_calculate_averages():
    # Arrange: Przygotowujemy czystą maciorę i symulujemy 1 cykl
    sow = Sow(sow_id="PL-123", ear_tag="1234", birth_date=date(2025, 1, 1))
    events = [
        SowEvent(event_type="INSEMINATION", event_date=date(2026, 1, 1), details={"technician": "Jan"}),
        SowEvent(event_type="FARROWING", event_date=date(2026, 4, 25), details={"born_alive": 14, "born_dead": 2}),
        SowEvent(event_type="WEANING", event_date=date(2026, 5, 23), details={"count": 11})
    ]

    # Act: Ładujemy historię
    sow.load_history(events)

    # Assert: Sprawdzamy podział na listy
    assert len(sow.inseminations) == 1
    assert len(sow.farrowings) == 1
    assert len(sow.weanings) == 1

    # Assert: Sprawdzamy obliczenia średnich na cykl
    assert sow.avg_born_alive == 14.0
    assert sow.avg_born_dead == 2.0
    assert sow.avg_weaned == 11.0
    assert sow.avg_loss_before_weaning == 3.0  # (14 urodzonych żywych - 11 odsadzonych = 3)


def test_should_prevent_negative_loss_on_data_error():
    # Co jeśli ktoś przez pomyłkę wpisze, że odsadzono więcej prosiąt niż się urodziło?
    sow = Sow(sow_id="PL-123", ear_tag="1234", birth_date=date(2025, 1, 1))
    events = [
        SowEvent(event_type="FARROWING", event_date=date(2026, 4, 25), details={"born_alive": 10, "born_dead": 0}),
        SowEvent(event_type="WEANING", event_date=date(2026, 5, 23), details={"count": 12})  # Odsadzono więcej?
    ]

    sow.load_history(events)

    # Straty nie mogą być ujemne, powinny wynosić 0.0
    assert sow.avg_loss_before_weaning == 0.0


def test_should_return_zeros_when_no_events_present():
    sow = Sow(sow_id="PL-123", ear_tag="1234", birth_date=date(2025, 1, 1))

    assert sow.avg_born_alive == 0.0
    assert sow.avg_born_dead == 0.0
    assert sow.avg_weaned == 0.0
    assert sow.avg_loss_before_weaning == 0.0