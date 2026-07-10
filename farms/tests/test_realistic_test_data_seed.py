from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import override_settings

from costs.models import CostModel
from farms.services.farm_service import get_or_create_user_farm
from feed.models import DeliveryModel, InventoryMovementModel, ProductionIngredientUsageModel, ProductionModel
from sales.models import PigSaleModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_seed_realistic_test_data_resets_testtest_and_keeps_other_farms_isolated():
    User = get_user_model()
    test_user = User.objects.create_user(username="testtest", password="old-password")
    old_farm = get_or_create_user_farm(test_user)
    SowModel.objects.create(farm=old_farm, ear_tag="DEMO-001")

    other_user = User.objects.create_user(username="other-owner", password="password")
    other_farm = get_or_create_user_farm(other_user)
    other_sow = SowModel.objects.create(farm=other_farm, ear_tag="9999")

    output = StringIO()
    call_command("seed_realistic_test_data", "--end-date=2026-07-08", stdout=output)

    test_user.refresh_from_db()
    farm = get_or_create_user_farm(test_user)
    assert test_user.check_password("testtest")
    assert farm.name == "Gospodarstwo trzody 2401"
    assert "demo" not in output.getvalue().lower()

    sows = SowModel.objects.filter(farm=farm)
    assert sows.count() == 10
    assert not sows.filter(ear_tag__icontains="demo").exists()
    assert SowModel.objects.filter(pk=other_sow.pk, farm=other_farm, ear_tag="9999").exists()

    event_types = set(SowEventModel.objects.filter(sow__farm=farm).values_list("event_type", flat=True))
    assert event_types == {value for value, _label in SowEventModel.EVENT_TYPES}
    event_dates = list(SowEventModel.objects.filter(sow__farm=farm).values_list("event_date", flat=True))
    assert min(event_dates).year == 2025
    assert max(event_dates).isoformat() <= "2026-07-08"
    assert {event_date.year for event_date in event_dates} == {2025, 2026}
    assert VaccinationPlanModel.objects.filter(farm=farm).count() == 4

    completed = ProductionModel.objects.filter(recipe__farm=farm, status=ProductionModel.Statuses.COMPLETED)
    assert completed.exists()
    assert not completed.filter(feed_cost_is_partial=True).exists()
    assert not completed.filter(ingredient_usages__isnull=True).exists()
    assert ProductionIngredientUsageModel.objects.filter(farm=farm).exists()
    assert InventoryMovementModel.objects.filter(farm=farm).exists()
    assert not DeliveryModel.objects.filter(ingredient__farm=farm, remaining_quantity_kg__lt=0).exists()

    sales = PigSaleModel.objects.filter(farm=farm)
    assert sales.count() == 8
    assert not sales.filter(no_settlement=True).exists()
    assert not sales.filter(rows__isnull=True).exists()
    assert CostModel.objects.filter(farm=farm, category__isnull=False, document_number__gt="").exists()


@pytest.mark.django_db
def test_seed_realistic_test_data_is_blocked_outside_debug():
    with override_settings(DEBUG=False):
        with pytest.raises(CommandError, match="wyłącznie lokalnie"):
            call_command("seed_realistic_test_data", "--end-date=2026-07-08", verbosity=0)
