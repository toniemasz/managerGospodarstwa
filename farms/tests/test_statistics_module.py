from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from costs.models import CostCategoryModel, CostModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.statistics import FarmStatisticsService
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from sales.models import PigSaleModel
from sows.models import MortalityReportModel, SowEventModel, SowModel


@pytest.fixture
def statistics_farms():
    User = get_user_model()
    owner = User.objects.create_user(username="stats-owner", password="pass")
    other = User.objects.create_user(username="stats-other", password="pass")
    return owner, get_or_create_user_farm(owner), get_or_create_user_farm(other)


def _create_feed_flow(farm):
    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica statystyczna")
    DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("2000.00"),
        price_per_kg=Decimal("1.50000"),
    )
    recipe = RecipeModel.objects.create(farm=farm, name="Grower statystyczny")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal("100.00"))
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("1000.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )
    production.refresh_from_db()
    return recipe, production


@pytest.mark.django_db
def test_statistics_service_calculates_feed_sales_and_profitability(statistics_farms):
    _, farm, _ = statistics_farms
    _create_feed_flow(farm)
    category = CostCategoryModel.objects.create(farm=farm, name="Energia")
    CostModel.objects.create(
        farm=farm,
        category=category,
        date=date(2026, 2, 5),
        amount=Decimal("500.00"),
        description="Prąd",
        is_paid=True,
    )
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 2, 10),
        quantity=10,
        total_weight=Decimal("900.00"),
        live_weight=Decimal("1200.00"),
        net_value=Decimal("8000.00"),
        gross_value=Decimal("8640.00"),
    )

    result = FarmStatisticsService(farm).calculate(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    assert result["sales"]["sold_quantity"] == 10
    assert result["feed"]["quantity_kg"] == Decimal("1000.00")
    assert result["feed"]["total_cost"] == Decimal("1500.00")
    assert result["costs"]["total"] == Decimal("500.00")
    assert result["profitability"]["net_result"] == Decimal("6000.00")
    assert result["feed_efficiency"]["feed_to_live_weight_ratio"] == Decimal("0.8333333333333333333333333333")
    assert result["production"]["completed_count"] == 1
    assert result["recipe_ranking"][0]["recipe_name"] == "Grower statystyczny"


@pytest.mark.django_db
def test_statistics_service_includes_mortality_summary(statistics_farms):
    _, farm, other_farm = statistics_farms
    sow = SowModel.objects.create(farm=farm, ear_tag="STAT-MORT-1")
    SowEventModel.objects.create(
        sow=sow,
        event_type="WEANING",
        event_date=date(2026, 1, 10),
        details={"count": 10},
    )
    MortalityReportModel.objects.create(
        farm=farm,
        mortality_type=MortalityReportModel.TYPE_SOW,
        sow=sow,
        mortality_date=date(2026, 2, 1),
        quantity=1,
    )
    MortalityReportModel.objects.create(
        farm=farm,
        mortality_type=MortalityReportModel.TYPE_POST_WEANING,
        mortality_date=date(2026, 2, 2),
        quantity=2,
    )
    MortalityReportModel.objects.create(
        farm=farm,
        mortality_type=MortalityReportModel.TYPE_POST_WEANING,
        mortality_date=date(2025, 12, 31),
        quantity=3,
    )
    other_sow = SowModel.objects.create(farm=other_farm, ear_tag="STAT-MORT-OTHER")
    SowEventModel.objects.create(
        sow=other_sow,
        event_type="WEANING",
        event_date=date(2026, 1, 10),
        details={"count": 20},
    )
    MortalityReportModel.objects.create(
        farm=other_farm,
        mortality_type=MortalityReportModel.TYPE_POST_WEANING,
        mortality_date=date(2026, 2, 2),
        quantity=9,
    )

    result = FarmStatisticsService(farm).calculate(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    assert result["mortality"]["sow_deaths"] == 1
    assert result["mortality"]["post_weaning_deaths"] == 2
    assert result["mortality"]["post_weaning_weaned_total"] == 10
    assert result["mortality"]["post_weaning_deaths_total"] == 5
    assert result["mortality"]["post_weaning_current_stock"] == 5


@pytest.mark.django_db
def test_statistics_view_is_farm_scoped(client, statistics_farms):
    owner, farm, other_farm = statistics_farms
    _create_feed_flow(farm)
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 2, 10),
        quantity=10,
        total_weight=Decimal("900.00"),
        live_weight=Decimal("1200.00"),
        net_value=Decimal("8000.00"),
        gross_value=Decimal("8640.00"),
    )
    PigSaleModel.objects.create(
        farm=other_farm,
        sale_date=date(2026, 2, 10),
        document_number="TAJNE-STAT",
        quantity=99,
        net_value=Decimal("99999.00"),
        gross_value=Decimal("99999.00"),
    )

    client.force_login(owner)
    response = client.get(reverse("farm_statistics"), {"year": "2026"})
    content = response.content.decode()

    assert response.status_code == 200
    assert response.context["sales"]["sold_quantity"] == 10
    assert "Grower statystyczny" in content
    assert "Stado i upadki" in content
    assert "Aplikacja nie ma jeszcze ewidencji obsady grup tuczowych i upadków" not in content
    assert "TAJNE-STAT" not in content
