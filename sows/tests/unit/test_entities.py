import pytest
from datetime import date, timedelta
from sows.services.sow_lifecycle import Sow, SowEvent


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

    def test_update_state_for_date_marks_sow_to_check_after_insemination_window(self, empty_sow):
        insem_date = date.today() - timedelta(days=30)
        empty_sow.load_history([
            SowEvent(event_type="INSEMINATION", event_date=insem_date, details={})
        ])

        empty_sow.update_state_for_date(date.today())

        assert empty_sow.status == "TO_CHECK"

    def test_not_due_for_pregnancy_check(self, empty_sow):
        insem_date = date.today() - timedelta(days=10)
        events = [SowEvent(event_type="INSEMINATION", event_date=insem_date, details={})]
        empty_sow.load_history(events)

        assert empty_sow.is_due_for_pregnancy_check(date.today()) is False


    def test_avg_loss_before_weaning_ignores_current_lactation(self, empty_sow):
        events = [
            SowEvent(event_type="FARROWING", event_date=date(2023, 1, 1), details={"born_alive": 10, "born_dead": 1}),
            SowEvent(event_type="WEANING", event_date=date(2023, 2, 1), details={"count": 8}),
            SowEvent(event_type="FARROWING", event_date=date(2023, 6, 1), details={"born_alive": 12, "born_dead": 0})
        ]
        empty_sow.load_history(events)
        assert empty_sow.avg_loss_before_weaning == 2.0

    def test_load_history_handles_negative_and_recheck_pregnancy_results(self, empty_sow):
        empty_sow.load_history([
            SowEvent(event_type="INSEMINATION", event_date=date(2023, 1, 1), details={}),
            SowEvent(event_type="PREGNANCY_CHECK", event_date=date(2023, 2, 1), details={"result": "?"}),
        ])
        assert empty_sow.status == "TO_RECHECK"

        empty_sow.load_history([
            SowEvent(event_type="INSEMINATION", event_date=date(2023, 3, 1), details={}),
            SowEvent(event_type="PREGNANCY_CHECK", event_date=date(2023, 4, 1), details={"result": "NIE"}),
        ])
        assert empty_sow.status == "IDLE"
        assert empty_sow.expected_farrowing_date is None

    def test_vaccination_does_not_change_main_status(self, empty_sow):
        empty_sow.load_history([
            SowEvent(event_type="INSEMINATION", event_date=date(2023, 1, 1), details={}),
            SowEvent(event_type="VACCINATION", event_date=date(2023, 1, 15), details={"vaccine_name": "Parwo"}),
        ])

        assert empty_sow.status == "INSEMINATED"

    def test_weaning_updates_average_and_status(self, empty_sow):
        empty_sow.load_history([
            SowEvent(event_type="FARROWING", event_date=date(2023, 1, 1), details={"born_alive": 11}),
            SowEvent(event_type="WEANING", event_date=date(2023, 2, 1), details={"count": 9}),
        ])

        assert empty_sow.status == "IDLE"
        assert empty_sow.total_weaned == 9
        assert empty_sow.avg_weaned == 9.0

    def test_dynamic_status_display_for_all_statuses(self, empty_sow):
        expected = {
            "INSEMINATED": "Po inseminacji",
            "TO_CHECK": "Do badania (USG)",
            "PREGNANT": "Prośna (Potwierdzona)",
            "TO_RECHECK": "Do rebadania (?)",
            "LACTATING": "Karmiąca",
            "IDLE": "Jałowa",
        }

        for status, label in expected.items():
            empty_sow.status = status
            assert empty_sow.dynamic_status_display == label
