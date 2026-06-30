from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from costs.forms import CostForm
from costs.models import CostCategoryModel, CostModel
from costs.services import CostService
from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm


@pytest.fixture
def cost_context(client):
    user = get_user_model().objects.create_user(username="cost-owner", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    return client, user, farm


@pytest.mark.django_db
def test_category_create_edit_and_deactivate_are_audited(cost_context):
    client, _user, farm = cost_context
    response = client.post(reverse("add_cost_category"), {"name": "Paliwo", "description": "Ciągniki"})
    category = CostCategoryModel.objects.get(farm=farm)
    assert response.status_code == 302

    client.post(reverse("edit_cost_category", args=[category.pk]), {"name": "Paliwo i oleje", "description": "Maszyny"})
    client.post(reverse("deactivate_cost_category", args=[category.pk]))
    category.refresh_from_db()

    assert category.name == "Paliwo i oleje"
    assert category.is_active is False
    assert list(AuditLogModel.objects.filter(farm=farm).values_list("action", flat=True)) == [
        "DEACTIVATE", "UPDATE", "CREATE"
    ]


@pytest.mark.django_db
def test_cost_create_edit_delete_form_and_audit(cost_context):
    client, user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    data = {
        "date": "2026-03-10",
        "amount": "450.50",
        "category": category.pk,
        "description": "Badanie stada",
        "document_number": "FV/3",
        "supplier": "Gabinet",
        "is_paid": "on",
    }
    response = client.post(reverse("add_cost"), data)
    cost = CostModel.objects.get(farm=farm)
    assert response.status_code == 302
    assert cost.created_by == user

    data.update({"amount": "500.00", "description": "Badanie i leki"})
    client.post(reverse("edit_cost", args=[cost.pk]), data)
    cost.refresh_from_db()
    assert cost.amount == Decimal("500.00")

    client.post(reverse("delete_cost", args=[cost.pk]))
    assert not CostModel.objects.filter(pk=cost.pk).exists()
    assert set(AuditLogModel.objects.filter(farm=farm).values_list("action", flat=True)) == {"CREATE", "UPDATE", "DELETE"}

    other_user = get_user_model().objects.create_user(username="cost-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_category = CostCategoryModel.objects.create(farm=other_farm, name="Obca")
    form = CostForm(data={**data, "category": foreign_category.pk}, farm=farm)
    assert not form.is_valid()


@pytest.mark.django_db
def test_cost_list_filters_summary_and_farm_isolation(cost_context):
    client, _user, farm = cost_context
    category_a = CostCategoryModel.objects.create(farm=farm, name="Energia")
    category_b = CostCategoryModel.objects.create(farm=farm, name="Transport")
    CostModel.objects.create(farm=farm, category=category_a, date=date(2026, 1, 2), amount=100, description="Prąd", is_paid=True)
    CostModel.objects.create(farm=farm, category=category_b, date=date(2026, 2, 2), amount=300, description="Przewóz", is_paid=False)
    CostModel.objects.create(farm=farm, category=category_a, date=date(2025, 1, 2), amount=900, description="Stary koszt")
    other_user = get_user_model().objects.create_user(username="hidden-cost")
    other_farm = get_or_create_user_farm(other_user)
    other_category = CostCategoryModel.objects.create(farm=other_farm, name="Sekret")
    CostModel.objects.create(farm=other_farm, category=other_category, date=date(2026, 1, 2), amount=9999, description="UKRYTY")

    response = client.get(reverse("cost_list"), {"year": 2026, "category": category_a.pk})
    content = response.content.decode()
    assert response.status_code == 200
    listed_descriptions = [cost.description for cost in response.context["costs"]]
    assert "Prąd" in content
    assert listed_descriptions == ["Prąd"]
    assert "UKRYTY" not in content
    assert response.context["summary"]["total"] == Decimal("100")

    summary = CostService.summarize(CostModel.objects.filter(farm=farm, date__year=2026))
    assert summary["paid"] == Decimal("100")
    assert summary["unpaid"] == Decimal("300")
    assert summary["largest_category"]["category__name"] == "Transport"


@pytest.mark.django_db
def test_empty_cost_list_has_clear_empty_state(cost_context):
    client, _user, _farm = cost_context
    response = client.get(reverse("cost_list"), {"year": 2026})
    assert "Brak kosztów" in response.content.decode()
