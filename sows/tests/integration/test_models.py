import pytest
from datetime import date
from sows.models import SowModel, SowEventModel, VaccinationPlanModel

@pytest.mark.django_db
class TestSowModels:
    def test_create_sow(self):
        sow = SowModel.objects.create(ear_tag="TEST-123", entry_date=date.today())
        assert sow.id is not None
        assert str(sow) == "Maciora TEST-123"

    def test_create_sow_event(self):
        sow = SowModel.objects.create(ear_tag="TEST-123")
        event = SowEventModel.objects.create(
            sow=sow,
            event_type="INSEMINATION",
            event_date=date.today(),
            details={"technician": "Jan Kowalski"}
        )
        assert event.id is not None
        assert event.sow.ear_tag == "TEST-123"
        assert event.details["technician"] == "Jan Kowalski"

    def test_create_vaccination_plan(self):
        plan = VaccinationPlanModel.objects.create(
            name="Parwowiroza",
            days_before_farrowing=21
        )
        assert str(plan) == "Parwowiroza"
