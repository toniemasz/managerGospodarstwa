from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from costs.models import CostModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.task_center import TaskCenterService
from feed.models import IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from sales.models import PigSaleModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


@pytest.mark.django_db
def test_task_center_has_three_tabs_sections_counts_empty_states_and_isolation(client):
    today = timezone.localdate()
    user = get_user_model().objects.create_user(username="tasks", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)

    usg_sow = SowModel.objects.create(farm=farm, ear_tag="USG-1", entry_date=today - timedelta(days=200))
    SowEventModel.objects.create(sow=usg_sow, event_type="INSEMINATION", event_date=today - timedelta(days=35))

    farrowing_sow = SowModel.objects.create(farm=farm, ear_tag="POROD-1", entry_date=today - timedelta(days=300))
    insemination = today - timedelta(days=110)
    SowEventModel.objects.create(sow=farrowing_sow, event_type="INSEMINATION", event_date=insemination)
    SowEventModel.objects.create(sow=farrowing_sow, event_type="PREGNANCY_CHECK", event_date=insemination + timedelta(days=30), details={"result": "TAK"})

    vaccination_sow = SowModel.objects.create(farm=farm, ear_tag="SZCZEP-1", entry_date=today - timedelta(days=30))
    VaccinationPlanModel.objects.create(farm=farm, name="Różyca", interval_months=1, reminder_days_ahead=7)

    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica", low_stock_threshold_kg=100)
    recipe = RecipeModel.objects.create(farm=farm, name="Grower")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    ProductionModel.objects.create(recipe=recipe, date=today, quantity_kg=1000, status=ProductionModel.Statuses.QUEUED)
    PigSaleModel.objects.create(farm=farm, sale_date=today, quantity=10, no_settlement=True)
    CostModel.objects.create(farm=farm, category=None, date=today, amount=100, description="Bez kategorii", is_paid=False)

    other_user = get_user_model().objects.create_user(username="tasks-other")
    other_farm = get_or_create_user_farm(other_user)
    PigSaleModel.objects.create(farm=other_farm, sale_date=today, quantity=99, no_settlement=True, document_number="SECRET")

    result = TaskCenterService(farm).get_tasks()
    assert list(result["tabs"]) == ["production", "feed", "finance"]
    assert result["tabs"]["production"]["count"] >= 3
    assert result["tabs"]["feed"]["count"] == 2
    assert result["tabs"]["finance"]["count"] == 2
    assert result["task_count"] == sum(tab["count"] for tab in result["tabs"].values())
    assert all(
        {"title", "description", "status_label", "priority", "due_date", "object_url", "action_url", "action_label", "metadata"} <= set(item)
        for tab in result["tabs"].values() for item in tab["items"]
    )

    response = client.get(reverse("task_center"), {"tab": "production"})
    content = response.content.decode()
    assert all(label in content for label in ["Produkcja", "Magazyn i pasza", "Finanse", "Badania USG", "Oproszenia", "Szczepienia"])
    assert all(identifier in content for identifier in ["USG-1", "POROD-1", "SZCZEP-1"])
    assert "SECRET" not in content

    empty_user = get_user_model().objects.create_user(username="empty-tasks", password="password")
    empty_farm = get_or_create_user_farm(empty_user)
    client.force_login(empty_user)
    for tab, message in [
        ("production", "W produkcji nie ma teraz zadań"),
        ("feed", "Magazyn i produkcja paszy nie wymagają"),
        ("finance", "Finanse nie mają teraz zadań"),
    ]:
        empty_response = client.get(reverse("task_center"), {"tab": tab})
        assert message in empty_response.content.decode()
    assert TaskCenterService(empty_farm).get_tasks()["task_count"] == 0
