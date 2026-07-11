from datetime import date

from sows.services.sow_repository import SowRepository, VaccinationPlanRepository
from sows.models import SowModel, SowEventModel, VaccinationPlanModel
import pytest
from farms.services.farm_service import get_or_create_legacy_farm


@pytest.mark.django_db
class TestSowRepository:
    @pytest.fixture
    def setup_sows(self):
        self.farm = get_or_create_legacy_farm()
        # Przygotowanie danych testowych
        self.active_sow = SowModel.objects.create(farm=self.farm, ear_tag="AKT-01", is_archived=False)
        self.archived_sow = SowModel.objects.create(farm=self.farm, ear_tag="ARCH-01", is_archived=True)
        self.repo = SowRepository(self.farm)

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
        farm = get_or_create_legacy_farm()
        # Arrange
        db_sow = SowModel.objects.create(farm=farm, ear_tag="MAP-1", entry_date=date(2023, 1, 1))
        SowEventModel.objects.create(sow=db_sow, event_type="INSEMINATION", event_date=date(2023, 2, 1))

        repo = SowRepository(farm)

        # Act
        sows = repo.get_all_sows()


        assert len(sows) == 1
        sow = sows[0]
        assert sow.ear_tag == "MAP-1"
        assert sow.status == "INSEMINATED"
        assert len(sow.all_events) == 1

    def test_get_sow_by_id(self):
        farm = get_or_create_legacy_farm()
        db_sow = SowModel.objects.create(farm=farm, ear_tag="ID-TEST")
        repo = SowRepository(farm)

        sow = repo.get_sow_by_id(db_sow.id)
        assert sow.ear_tag == "ID-TEST"


@pytest.mark.django_db
def test_vaccination_plan_repository_public_methods():
    farm = get_or_create_legacy_farm()
    VaccinationPlanModel.objects.create(farm=farm, name="ZZZ", days_before_farrowing=21)
    VaccinationPlanModel.objects.create(farm=farm, name="AAA", interval_months=4)

    repo = VaccinationPlanRepository(farm)

    assert [plan.name for plan in repo.get_all_plans()] == ["AAA", "ZZZ"]
    assert repo.get_plan_choices() == [
        ('', '--- Wybierz szczepienie cykliczne ---'),
        ('AAA', 'AAA'),
        ('ZZZ', 'ZZZ'),
    ]
