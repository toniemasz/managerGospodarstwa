# sows/tests/integration/test_repositories.py
import pytest
from datetime import date
from sows.models import SowModel, SowEventModel
from sows.infrastructure.repositories import SowRepository

@pytest.mark.django_db
def test_repository_maps_django_model_to_domain_entity():
    # Arrange: Zapisujemy prawdziwe dane w testowej bazie SQLite
    db_sow = SowModel.objects.create(sow_id="PL-999", ear_tag="999", birth_date=date(2025, 1, 1))
    SowEventModel.objects.create(
        sow=db_sow,
        event_type="INSEMINATION",
        event_date=date(2026, 1, 1),
        details={"technician": "Marek"}
    )

    repo = SowRepository()

    # Act: Pobieramy dane przez repozytorium
    domain_sow = repo.get_sow_by_id("PL-999")

    # Assert: Sprawdzamy czy to prawdziwy obiekt domenowy Sow
    assert domain_sow.sow_id == "PL-999"
    assert domain_sow.ear_tag == "999"
    assert domain_sow.status == "INSEMINATED"
    assert len(domain_sow.inseminations) == 1
    assert domain_sow.inseminations[0].details["technician"] == "Marek"