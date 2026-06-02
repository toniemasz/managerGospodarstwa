from datetime import date

from sows.infrastructure.repositories import SowRepository
from sows.models import SowModel, SowEventModel
import pytest


@pytest.mark.django_db
class TestSowRepository:
    @pytest.fixture
    def setup_sows(self):
        # Przygotowanie danych testowych
        self.active_sow = SowModel.objects.create(ear_tag="AKT-01", is_archived=False)
        self.archived_sow = SowModel.objects.create(ear_tag="ARCH-01", is_archived=True)
        self.repo = SowRepository()

    def test_get_all_sows_returns_only_active(self, setup_sows):
        sows = self.repo.get_all_sows()

        assert len(sows) == 1
        assert sows[0].ear_tag == "AKT-01"
        assert sows[0].is_archived is False

    def test_get_archived_sows_returns_only_archived(self, setup_sows):
        archived_sows = self.repo.get_archived_sows()

        assert len(archived_sows) == 1
        assert archived_sows[0].ear_tag == "ARCH-01"
        assert archived_sows[0].is_archived is True

    def test_get_all_sows_mapping(self):
        # Arrange
        db_sow = SowModel.objects.create(ear_tag="MAP-1", entry_date=date(2023, 1, 1))
        SowEventModel.objects.create(sow=db_sow, event_type="INSEMINATION", event_date=date(2023, 2, 1))

        repo = SowRepository()

        # Act
        sows = repo.get_all_sows()


        assert len(sows) == 1
        domain_sow = sows[0]
        assert domain_sow.ear_tag == "MAP-1"
        assert domain_sow.status == "INSEMINATED"  
        assert len(domain_sow.all_events) == 1

    def test_get_sow_by_id(self):
        db_sow = SowModel.objects.create(ear_tag="ID-TEST")
        repo = SowRepository()

        domain_sow = repo.get_sow_by_id(db_sow.id)
        assert domain_sow.ear_tag == "ID-TEST"