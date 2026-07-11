import pytest
from datetime import date
from sows.models import SowModel, SowEventModel, VaccinationPlanModel
from farms.services.farm_service import get_or_create_legacy_farm

@pytest.mark.django_db
class TestSowModels:
    def test_create_sow(self):
        farm = get_or_create_legacy_farm()
        sow = SowModel.objects.create(farm=farm, ear_tag="TEST-123", entry_date=date.today())
        assert sow.id is not None
        assert str(sow) == "Maciora TEST-123"
        assert sow.is_archived is False

    def test_create_sow_event(self):
        farm = get_or_create_legacy_farm()
        sow = SowModel.objects.create(farm=farm, ear_tag="TEST-123")
        event = SowEventModel.objects.create(
            sow=sow,
            event_type="INSEMINATION",
            event_date=date.today(),
            details={"technician": "Jan Kowalski"}
        )
        assert event.id is not None
        assert event.sow.ear_tag == "TEST-123"
        assert event.details["technician"] == "Jan Kowalski"
        assert str(event).startswith("INSEMINATION")

    def test_create_vaccination_plan(self):
        farm = get_or_create_legacy_farm()
        plan = VaccinationPlanModel.objects.create(
            farm=farm,
            name="Parwowiroza",
            days_before_farrowing=21
        )
        assert str(plan) == "Parwowiroza"
