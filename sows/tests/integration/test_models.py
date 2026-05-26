from datetime import date
import pytest
from sows.models import SowModel, SowEventModel
from sows.domain.entities import Sow, SowEvent

@pytest.mark.django_db
def test_should_map_database_model_to_domain_entity():
    db_sow = SowModel.objects.create(sow_id="PL-DB-1", ear_tag="9999", birth_date=date(2025, 1, 1))
    SowEventModel.objects.create(sow=db_sow, event_type="INSEMINATION", event_date=date(2026, 5, 1), details={"technician": "Adam"})
    
    sow_entity = Sow(sow_id=db_sow.sow_id, ear_tag=db_sow.ear_tag, birth_date=db_sow.birth_date)
    domain_events = [SowEvent(event_type=e.event_type, event_date=e.event_date, details=e.details) for e in db_sow.events.all()]
    sow_entity.load_history(domain_events)
    
    assert sow_entity.status == "INSEMINATED"



@pytest.mark.django_db
def test_should_save_new_sow_to_database():
    sow_id = "PL-DB-NEW"
    ear_tag = "5555"
    birth_date = date(2025, 6, 1)

    new_sow = SowModel.objects.create(
        sow_id=sow_id,
        ear_tag=ear_tag,
        birth_date=birth_date
    )

    fetched_sow = SowModel.objects.get(sow_id=sow_id)
    assert fetched_sow.ear_tag == "5555"
    assert fetched_sow.birth_date == date(2025, 6, 1)
    assert SowModel.objects.count() == 1
