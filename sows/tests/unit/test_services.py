# sows/tests/unit/test_services.py
from datetime import date
from unittest.mock import Mock
from sows.domain.entities import Sow
from sows.application.services import SowDashboardService


def test_dashboard_service_calculates_summaries_correctly():
    # Arrange: Tworzymy atrapy macior (bez bazy danych!)
    sow_inseminated = Sow(sow_id="1", ear_tag="111", birth_date=date(2025, 1, 1))
    sow_inseminated.status = "INSEMINATED"

    sow_lactating = Sow(sow_id="2", ear_tag="222", birth_date=date(2025, 1, 1))
    sow_lactating.status = "LACTATING"

    sow_idle = Sow(sow_id="3", ear_tag="333", birth_date=date(2025, 1, 1))
    sow_idle.status = "IDLE"

    mock_repository = Mock()
    mock_repository.get_all_sows.return_value = [sow_inseminated, sow_lactating, sow_idle]

    service = SowDashboardService(repository=mock_repository)


    summary = service.get_dashboard_summary()


    assert summary['total_sows'] == 3
    assert summary['inseminated_count'] == 1
    assert summary['lactating_count'] == 1
    assert summary['idle_count'] == 1
    mock_repository.get_all_sows.assert_called_once()