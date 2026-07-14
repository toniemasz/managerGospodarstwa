from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from costs.models import CostCategoryModel, CostModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.accounting_year import get_available_years
from farms.services.statistics import FarmStatisticsService
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.actions.productions import complete_production
from feed.actions.inventory import InventoryActions
from sales.models import PigSaleModel
from sows.models import MortalityReportModel, SowEventModel, SowModel
from sows.services.reporting import SowReportingService


@pytest.fixture
def statistics_farms():
    User = get_user_model()
    owner = User.objects.create_user(username="stats-owner", password="pass")
    other = User.objects.create_user(username="stats-other", password="pass")
    return owner, get_or_create_user_farm(owner), get_or_create_user_farm(other)


def _create_feed_flow(farm):
    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica statystyczna")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("2000.00"),
        price_per_kg=Decimal("1.50000"),
    )
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="Grower statystyczny")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal("100.00"))
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("1000.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    success, message = complete_production(farm, production.pk, user=farm.owner)
    assert success, message
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
    assert result["costs"]["total"] == Decimal("2000.00")
    assert result["additional_costs"]["total"] == Decimal("500.00")
    assert result["profitability"]["net_result"] == Decimal("6000.00")
    assert result["feed_efficiency"]["feed_to_live_weight_ratio"] == Decimal("0.8333333333333333333333333333")
    assert result["production"]["completed_count"] == 1
    assert result["recipe_ranking"][0]["recipe_name"] == "Grower statystyczny"


@pytest.mark.django_db
def test_statistics_take_feed_amount_from_cost_registry(statistics_farms):
    _, farm, _ = statistics_farms
    _, production = _create_feed_flow(farm)
    assert production.feed_cost_total == Decimal("1500.00")
    cost = CostModel.objects.get(production=production)
    cost.amount = Decimal("1234.00")
    cost.save(update_fields=("amount", "updated_at"))

    result = FarmStatisticsService(farm).calculate(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    assert result["feed"]["total_cost"] == Decimal("1234.00")
    assert result["costs"]["total"] == Decimal("1234.00")
    assert result["profitability"]["total_cost"] == Decimal("1234.00")


@pytest.mark.django_db
def test_statistics_detect_missing_feed_cost_sync_without_double_counting_snapshot(statistics_farms):
    _, farm, _ = statistics_farms
    _, production = _create_feed_flow(farm)
    CostModel.objects.filter(production=production).delete()

    result = FarmStatisticsService(farm).calculate(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    assert production.feed_cost_total == Decimal("1500.00")
    assert result["feed"]["total_cost"] == Decimal("0.00")
    assert result["costs"]["total"] == Decimal("0.00")
    assert result["feed"]["missing_sync_count"] == 1


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
    assert result["mortality"]["period"]["post_weaning_deaths"] == 2
    assert result["mortality"]["current_snapshot"]["post_weaning_deaths_total"] == 5


@pytest.mark.django_db
def test_sow_reporting_includes_archived_history_and_is_farm_scoped(statistics_farms):
    _, farm, other_farm = statistics_farms
    active = SowModel.objects.create(farm=farm, ear_tag="STAT-SOW-A")
    archived = SowModel.objects.create(farm=farm, ear_tag="STAT-SOW-H", is_archived=True)
    foreign = SowModel.objects.create(farm=other_farm, ear_tag="STAT-SOW-X")
    SowEventModel.objects.create(
        sow=active,
        event_type="FARROWING",
        event_date=date(2026, 2, 1),
        details={"born_alive": 10, "born_dead": 1},
    )
    SowEventModel.objects.create(
        sow=archived,
        event_type="FARROWING",
        event_date=date(2026, 3, 1),
        details={"born_alive": 12, "born_dead": 2},
    )
    SowEventModel.objects.create(
        sow=foreign,
        event_type="FARROWING",
        event_date=date(2026, 3, 1),
        details={"born_alive": 99, "born_dead": 9},
    )

    result = SowReportingService(farm).summary(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )

    assert result["active_sows"] == 1
    assert result["archived_sows"] == 1
    assert result["farrowings"] == 2
    assert result["born_alive"] == 22
    assert result["born_dead"] == 3
    assert result["average_born_alive_per_litter"] == Decimal("11")


@pytest.mark.django_db
def test_available_statistics_years_include_sow_events_and_mortality(statistics_farms):
    _, farm, _other_farm = statistics_farms
    sow = SowModel.objects.create(farm=farm, ear_tag="STAT-YEAR")
    SowEventModel.objects.create(
        sow=sow,
        event_type="FARROWING",
        event_date=date(2024, 4, 1),
        details={"born_alive": 10},
    )
    MortalityReportModel.objects.create(
        farm=farm,
        mortality_type=MortalityReportModel.TYPE_PIGLET,
        mortality_date=date(2023, 5, 1),
        quantity=1,
    )

    years = get_available_years(farm)

    assert 2024 in years
    assert 2023 in years


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


@pytest.mark.django_db
@pytest.mark.parametrize("section", FarmStatisticsService.SECTION_KEYS)
def test_each_statistics_section_has_own_view_and_uses_central_service(client, statistics_farms, section):
    owner, _farm, _other_farm = statistics_farms
    client.force_login(owner)

    response = client.get(reverse("farm_statistics_section", args=[section]), {"year": "2026"})

    assert response.status_code == 200
    assert response.context["active_section"] == section
    assert response.context["section_cards"]
    expected_data_key = {
        "profitability": "profitability",
        "sales": "sales",
        "sows": "sows",
        "mortality": "mortality",
        "feed": "feed",
        "inventory": "inventory",
        "costs": "costs",
    }[section]
    assert expected_data_key in response.context
    active_links = [link for link in response.context["statistic_links"] if link["is_active"]]
    assert [link["url"] for link in active_links] == [reverse("farm_statistics_section", args=[section])]


@pytest.mark.django_db
def test_unknown_statistics_section_returns_404(client, statistics_farms):
    owner, _farm, _other_farm = statistics_farms
    client.force_login(owner)
    assert client.get(reverse("farm_statistics_section", args=["nie-istnieje"])).status_code == 404


def test_statistics_navigation_points_only_to_statistics_views():
    links = FarmStatisticsService.statistic_links()
    assert links[0]["url"] == reverse("farm_statistics")
    assert all(link["url"].startswith("/statystyki/") for link in links)
