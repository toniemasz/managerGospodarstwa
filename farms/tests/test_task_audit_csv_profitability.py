from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from farms.models import AuditLogModel
from farms.services.audit_log_service import log_action
from farms.services.csv_transfer import build_csv_export, import_csv_archive
from farms.services.farm_service import get_or_create_user_farm
from farms.services.profitability import ProfitabilityAnalyticsService
from farms.services.task_center import TaskCenterService
from costs.models import CostCategoryModel, CostModel
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.actions.productions import complete_production
from feed.actions.inventory import InventoryActions
from sales.models import PigSaleModel
from sows.models import (
    MortalityReportModel,
    PigletTransferModel,
    SowEventModel,
    SowModel,
    VaccinationCycleModel,
    VaccinationPlanModel,
)


@pytest.fixture
def two_farms():
    first = User.objects.create_user(username="farm-a", password="pass")
    second = User.objects.create_user(username="farm-b", password="pass")
    return first, get_or_create_user_farm(first), second, get_or_create_user_farm(second)


@pytest.mark.django_db
def test_task_center_and_audit_log_are_isolated(client, two_farms):
    user_a, farm_a, _, farm_b = two_farms
    ingredient_a = IngredientModel.objects.create(farm=farm_a, name="A", low_stock_threshold_kg=100)
    IngredientModel.objects.create(farm=farm_b, name="B", low_stock_threshold_kg=100)
    sale_a = PigSaleModel.objects.create(farm=farm_a, no_settlement=True)
    PigSaleModel.objects.create(farm=farm_b, no_settlement=True)
    log_action(farm=farm_a, user=user_a, action="CREATE", obj=sale_a)
    log_action(farm=farm_b, action="SECRET", obj=ingredient_a, object_repr="other farm")

    tasks = TaskCenterService(farm_a).get_tasks()
    assert [item.name for item in tasks["low_stock"]] == ["A"]
    assert list(tasks["unsettled_sales"]) == [sale_a]

    client.force_login(user_a)
    task_response = client.get(reverse("task_center"), {"tab": "feed"})
    assert task_response.status_code == 200
    assert b"Niski stan: A" in task_response.content
    assert b"Niski stan: B" not in task_response.content
    response = client.get(reverse("audit_log"))
    assert response.status_code == 200
    assert b"SECRET" not in response.content
    filtered = client.get(reverse("audit_log"), {"action": "SECRET"})
    assert filtered.status_code == 200
    assert list(filtered.context["logs"]) == []


@pytest.mark.django_db
def test_csv_export_and_atomic_import_round_trip(two_farms):
    _, source, _, target = two_farms
    sow = SowModel.objects.create(farm=source, ear_tag="CSV-1")
    plan = VaccinationPlanModel.objects.create(
        farm=source,
        name="CSV szczepienie",
        interval_value=6,
        interval_unit="WEEKS",
        schedule_mode="FIXED",
        first_due_date=date.today(),
        scope="SELECTED",
    )
    plan.selected_sows.add(sow)
    VaccinationCycleModel.objects.create(
        plan=plan,
        sow=sow,
        cycle_id="csv-cycle",
        scheduled_date=date.today(),
        status="SKIPPED",
        skipped_at=date.today(),
        note="CSV test",
    )
    ingredient = IngredientModel.objects.create(farm=source, name="Pszenica")
    delivery = DeliveryModel.objects.create(ingredient=ingredient, date=date.today(), quantity_kg=1000, price_per_kg=1)
    InventoryActions(source).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=source, name="CSV recipe")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date.today(),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    assert complete_production(source, production.pk, user=source.owner)[0]
    PigSaleModel.objects.create(farm=source, document_number="CSV/1", quantity=10)
    category = CostCategoryModel.objects.create(farm=source, name="CSV koszt")
    CostModel.objects.create(
        farm=source,
        category=category,
        date=date.today(),
        amount=Decimal("123.45"),
        description="Koszt z CSV",
        is_paid=True,
    )

    payload, _ = build_csv_export(source)
    uploaded = SimpleUploadedFile("export.zip", payload, content_type="application/zip")
    counts = import_csv_archive(uploaded, target)
    production.refresh_from_db()

    assert counts["maciory"] == 1
    assert counts["cykle szczepień"] == 1
    assert SowModel.objects.filter(farm=target, ear_tag=sow.ear_tag).exists()
    assert IngredientModel.objects.filter(farm=target, name="Pszenica").exists()
    assert CostModel.objects.filter(farm=target, description="Koszt z CSV", amount=Decimal("123.45")).exists()
    restored_plan = VaccinationPlanModel.objects.get(farm=target)
    assert restored_plan.interval_value == 6
    assert list(restored_plan.selected_sows.values_list("ear_tag", flat=True)) == ["CSV-1"]
    assert VaccinationCycleModel.objects.get(plan=restored_plan).note == "CSV test"
    restored_production = ProductionModel.objects.get(recipe__farm=target, recipe__name=recipe.name)
    assert CostModel.objects.filter(
        farm=target,
        production=restored_production,
        amount=production.feed_cost_total,
    ).exists()
    assert not SowModel.objects.filter(farm=source).exclude(pk=sow.pk).exists()


@pytest.mark.django_db
def test_csv_round_trip_preserves_piglet_care_relationships(two_farms):
    _, source, _, target = two_farms
    source_sow = SowModel.objects.create(farm=source, ear_tag="CSV-A")
    target_sow = SowModel.objects.create(farm=source, ear_tag="CSV-B")
    source_farrowing = SowEventModel.objects.create(
        sow=source_sow,
        event_type="FARROWING",
        event_date=date(2026, 2, 1),
        details={"born_alive": 12},
    )
    target_farrowing = SowEventModel.objects.create(
        sow=target_sow,
        event_type="FARROWING",
        event_date=date(2026, 2, 2),
        details={"born_alive": 8},
    )
    PigletTransferModel.objects.create(
        farm=source,
        source_farrowing=source_farrowing,
        target_farrowing=target_farrowing,
        quantity=3,
        transfer_date=date(2026, 2, 5),
    )
    MortalityReportModel.objects.create(
        farm=source,
        sow=target_sow,
        farrowing=target_farrowing,
        mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
        mortality_date=date(2026, 2, 6),
        quantity=1,
    )

    payload, _ = build_csv_export(source)
    uploaded = SimpleUploadedFile("piglet-care.zip", payload, content_type="application/zip")
    counts = import_csv_archive(uploaded, target)

    restored_transfer = PigletTransferModel.objects.get(farm=target)
    assert counts["przeniesienia prosiąt"] == 1
    assert restored_transfer.source_sow.ear_tag == "CSV-A"
    assert restored_transfer.target_sow.ear_tag == "CSV-B"
    restored_mortality = MortalityReportModel.objects.get(farm=target)
    assert restored_mortality.farrowing == restored_transfer.target_farrowing


@pytest.mark.django_db
def test_settings_view_imports_csv_archive_into_empty_farm(client, two_farms):
    _, source, target_user, target = two_farms
    sow = SowModel.objects.create(farm=source, ear_tag="CSV-VIEW-1")
    ingredient = IngredientModel.objects.create(farm=source, name="CSV view składnik")
    recipe = RecipeModel.objects.create(farm=source, name="CSV view recipe")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    payload, _ = build_csv_export(source)
    client.force_login(target_user)

    response = client.post(reverse("farm_settings"), {
        "import_csv": "1",
        "confirm_empty_import": "on",
        "csv_archive": SimpleUploadedFile("export.zip", payload, content_type="application/zip"),
    })

    assert response.status_code == 302
    assert SowModel.objects.filter(farm=target, ear_tag=sow.ear_tag).exists()
    assert RecipeModel.objects.filter(farm=target, name=recipe.name).exists()
    assert AuditLogModel.objects.filter(farm=target, action="CSV_IMPORT").exists()


@pytest.mark.django_db
def test_settings_view_blocks_csv_import_into_non_empty_farm(client, two_farms):
    _, source, target_user, target = two_farms
    SowModel.objects.create(farm=source, ear_tag="CSV-SOURCE")
    SowModel.objects.create(farm=target, ear_tag="CSV-EXISTING")
    payload, _ = build_csv_export(source)
    client.force_login(target_user)

    response = client.post(reverse("farm_settings"), {
        "import_csv": "1",
        "confirm_empty_import": "on",
        "csv_archive": SimpleUploadedFile("export.zip", payload, content_type="application/zip"),
    })

    assert response.status_code == 302
    assert list(SowModel.objects.filter(farm=target).values_list("ear_tag", flat=True)) == ["CSV-EXISTING"]
    assert not AuditLogModel.objects.filter(farm=target, action="CSV_IMPORT").exists()


@pytest.mark.django_db
def test_csv_import_rejects_broken_archive_without_partial_writes(two_farms):
    _, _, _, target = two_farms
    uploaded = SimpleUploadedFile("broken.zip", b"not-a-zip", content_type="application/zip")
    with pytest.raises(ValueError):
        import_csv_archive(uploaded, target)
    assert not SowModel.objects.filter(farm=target).exists()


@pytest.mark.django_db
def test_profitability_calculations_are_farm_scoped(two_farms):
    _, farm, _, other = two_farms
    ingredient = IngredientModel.objects.create(farm=farm, name="Zboże")
    delivery = DeliveryModel.objects.create(ingredient=ingredient, date=date.today(), quantity_kg=2000, price_per_kg=Decimal("1.50"))
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="Pasza")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date.today(),
        quantity_kg=1000,
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    assert complete_production(farm, production.pk, user=farm.owner)[0]
    PigSaleModel.objects.create(farm=farm, sale_date=date.today(), quantity=10, total_weight=1000, net_value=8000, gross_value=8640)
    PigSaleModel.objects.create(farm=other, sale_date=date.today(), quantity=99, net_value=99999, gross_value=99999)

    result = ProfitabilityAnalyticsService(farm).calculate()
    assert result["net_sales"] == Decimal("8000")
    assert result["sold_quantity"] == 10
    assert result["feed_quantity_kg"] == Decimal("1000")
    assert result["feed_cost"] == Decimal("1500")


@pytest.mark.django_db
def test_profitability_includes_manual_costs_and_monthly_result(two_farms):
    _, farm, _, _other = two_farms
    category = CostCategoryModel.objects.create(farm=farm, name="Energia")
    CostModel.objects.create(
        farm=farm,
        category=category,
        date=date(2026, 3, 5),
        amount=Decimal("1200"),
        description="Prąd",
        is_paid=True,
    )
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 3, 20),
        quantity=10,
        live_weight=Decimal("1200"),
        net_value=Decimal("10000"),
        gross_value=Decimal("10800"),
    )
    result = ProfitabilityAnalyticsService(farm).calculate(
        date_from=date(2026, 1, 1),
        date_to=date(2026, 12, 31),
    )
    assert result["additional_cost"] == Decimal("1200")
    assert result["net_result"] == Decimal("8800")
    assert result["total_cost_per_live_kg"] == Decimal("1")
    assert result["timeline"][0]["result_net"] == Decimal("8800")


@pytest.mark.django_db
def test_csv_cost_export_is_filtered_by_accounting_year(two_farms):
    _, source, _, _target = two_farms
    category = CostCategoryModel.objects.create(farm=source, name="Eksport")
    CostModel.objects.create(farm=source, category=category, date=date(2025, 1, 1), amount=10, description="Rok 2025")
    CostModel.objects.create(farm=source, category=category, date=date(2026, 1, 1), amount=20, description="Rok 2026")

    payload, _ = build_csv_export(source, year=2026)
    from zipfile import ZipFile
    with ZipFile(BytesIO(payload)) as archive:
        exported = archive.read("costs.csv").decode("utf-8-sig")
    assert "Rok 2026" in exported
    assert "Rok 2025" not in exported
