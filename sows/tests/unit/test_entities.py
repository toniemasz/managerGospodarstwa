import pytest
from datetime import date, timedelta
from sows.domain.entities import Sow, SowEvent


class TestSowEntity:
    @pytest.fixture
    def empty_sow(self):
        return Sow(id=1, ear_tag="PL123", entry_date=date(2023, 1, 1), created_at=date(2023, 1, 1))

    def test_initial_status(self, empty_sow):
        assert empty_sow.status == "IDLE"
        assert empty_sow.total_born_alive == 0

    def test_load_history_insemination(self, empty_sow):
        events = [
            SowEvent(event_type="INSEMINATION", event_date=date(2023, 5, 1), details={})
        ]
        empty_sow.load_history(events)

        assert empty_sow.status == "INSEMINATED"
        assert empty_sow.last_insemination_date == date(2023, 5, 1)
        assert empty_sow.expected_farrowing_date == date(2023, 5, 1) + timedelta(days=114)

    def test_load_history_pregnancy_check_positive(self, empty_sow):
        events = [
            SowEvent(event_type="PREGNANCY_CHECK", event_date=date(2023, 6, 1), details={"result": "TAK"})
        ]
        empty_sow.load_history(events)

        assert empty_sow.status == "PREGNANT"

    def test_load_history_farrowing_updates_stats(self, empty_sow):
        events = [
            SowEvent(event_type="FARROWING", event_date=date(2023, 8, 20), details={"born_alive": 12, "born_dead": 1})
        ]
        empty_sow.load_history(events)

        assert empty_sow.status == "LACTATING"
        assert empty_sow.total_born_alive == 12
        assert empty_sow.total_born_dead == 1
        assert empty_sow.farrowing_count == 1
        assert empty_sow.avg_born_alive == 12.0

    def test_is_due_for_pregnancy_check(self, empty_sow):

        insem_date = date.today() - timedelta(days=30)
        events = [SowEvent(event_type="INSEMINATION", event_date=insem_date, details={})]
        empty_sow.load_history(events)

        assert empty_sow.is_due_for_pregnancy_check(date.today()) is True

    def test_not_due_for_pregnancy_check(self, empty_sow):
        insem_date = date.today() - timedelta(days=10)
        events = [SowEvent(event_type="INSEMINATION", event_date=insem_date, details={})]
        empty_sow.load_history(events)

        assert empty_sow.is_due_for_pregnancy_check(date.today()) is False