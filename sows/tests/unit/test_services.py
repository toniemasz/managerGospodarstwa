import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date
from sows.services.sow_dashboard_service import SowDashboardService
from sows.services.sow_lifecycle import Sow, SowEvent

class TestSowDashboardService:
    @pytest.fixture
    def mock_repo(self):
        repo = Mock()
        sow1 = Sow(id=1, ear_tag="SOW-1", entry_date=date(2023, 1, 1), created_at=date(2023, 1, 1))
        sow1.status = "INSEMINATED"
        sow2 = Sow(id=2, ear_tag="SOW-2", entry_date=date(2023, 1, 1), created_at=date(2023, 1, 1))
        sow2.status = "PREGNANT"
        repo.get_all_sows.return_value = [sow1, sow2]
        return repo

    @patch('sows.services.sow_dashboard_service.VaccinationPlanModel.objects.all')
    def test_get_dashboard_summary(self, mock_db_plans, mock_repo):
        # Arrange
        mock_db_plans.return_value = []
        service = SowDashboardService(repository=mock_repo)

        # Act
        summary = service.get_dashboard_summary()

        # Assert
        assert summary['total_sows'] == 2
        assert summary['inseminated_count'] == 1
        assert summary['pregnant_count'] == 1
        assert summary['idle_count'] == 0
        assert mock_repo.get_all_sows.called


    def test_get_archived_sows_list(self):
        # Arrange - Przygotowujemy zamockowane dane
        mock_sow = MagicMock(spec=Sow)
        mock_sow.ear_tag = "ARCH-TEST"

        mock_repo = Mock()

        mock_repo.get_archived_sows.return_value = [mock_sow]


        service = SowDashboardService()
        service.repository = mock_repo

        # Act
        result = service.get_archived_sows_list()


        mock_repo.get_archived_sows.assert_called_once()
        mock_sow.update_state_for_date.assert_called_once_with(date.today())

        assert len(result) == 1
        assert result[0] == mock_sow

    def test_get_general_statistics_uses_metric_and_ordering(self):
        sow1 = Sow(id=1, ear_tag="A", entry_date=date(2023, 1, 1), created_at=date(2023, 1, 1))
        sow1.status = "IDLE"
        sow1.load_history([
            SowEvent(event_type="FARROWING", event_date=date.today(), details={"born_alive": 12})
        ])
        sow2 = Sow(id=2, ear_tag="B", entry_date=date(2023, 1, 1), created_at=date(2023, 1, 1))
        sow2.status = "IDLE"
        sow2.load_history([
            SowEvent(event_type="FARROWING", event_date=date.today(), details={"born_alive": 8})
        ])
        mock_repo = Mock()
        mock_repo.get_all_sows.return_value = [sow1, sow2]

        result = SowDashboardService(repository=mock_repo).get_general_statistics(
            metric_key="unknown",
            months_limit=0,
            order="asc",
        )

        assert result['current_metric'].key == "born_alive"
        assert [item['ear_tag'] for item in result['top_sows']] == ["B", "A"]
        assert result['chart_values'] == [20]
