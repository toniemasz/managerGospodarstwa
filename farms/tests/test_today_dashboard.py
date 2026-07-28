from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from costs.models import CostModel
from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from farms.services.task_center import TaskCenterService
from farms.services.today_dashboard import TodayDashboardService
from feed.models import IngredientModel
from sales.models import PigSaleModel
from sows.models import MortalityReportModel, SowEventModel, SowModel, VaccinationPlanModel


@pytest.fixture
def today_dashboard_client(client):
    user = get_user_model().objects.create_user(username="today-owner", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    client.farm = farm
    return client


@pytest.mark.django_db
def test_today_dashboard_loads_task_cards_kpis_recent_events_and_is_farm_scoped(today_dashboard_client):
    today = timezone.localdate()
    farm = today_dashboard_client.farm

    sow = SowModel.objects.create(farm=farm, ear_tag="TODAY-USG", entry_date=today - timedelta(days=200))
    SowEventModel.objects.create(
        sow=sow,
        event_type="INSEMINATION",
        event_date=today - timedelta(days=35),
    )
    vaccination_sow = SowModel.objects.create(
        farm=farm,
        ear_tag="TODAY-VACCINE",
        entry_date=today - timedelta(days=30),
    )
    VaccinationPlanModel.objects.create(
        farm=farm,
        name="Parwo",
        interval_value=1,
        interval_unit="MONTHS",
        schedule_mode="FIXED",
        first_due_date=today,
        reminder_days_ahead=7,
    )
    IngredientModel.objects.create(
        farm=farm,
        name="TODAY-WHEAT",
        low_stock_threshold_kg=Decimal("100.00"),
    )
    MortalityReportModel.objects.create(
        farm=farm,
        mortality_type=MortalityReportModel.TYPE_POST_WEANING,
        mortality_date=today,
        quantity=2,
    )
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=today,
        document_number="TODAY-SALE",
        quantity=5,
        net_value=Decimal("1234.00"),
        gross_value=Decimal("1332.72"),
    )
    CostModel.objects.create(
        farm=farm,
        date=today,
        amount=Decimal("321.00"),
        description="TODAY-COST",
        is_paid=False,
    )

    other_user = get_user_model().objects.create_user(username="today-other")
    other_farm = get_or_create_user_farm(other_user)
    other_sow = SowModel.objects.create(farm=other_farm, ear_tag="SECRET-SOW")
    SowEventModel.objects.create(
        sow=other_sow,
        event_type="INSEMINATION",
        event_date=today,
    )
    PigSaleModel.objects.create(
        farm=other_farm,
        sale_date=today,
        document_number="SECRET-SALE",
        quantity=99,
    )

    response = today_dashboard_client.get(reverse("modules_home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "mobile-quick-dashboard" in content
    assert "wide-dashboard" in content
    assert "mobile-mode-switch" not in content
    assert "mobile-dashboard-switch" not in content
    assert "Dzisiaj" in content
    assert "Dodaj wpis po numerze kolczyka" in content
    assert "Zgłoś upadek" in content
    assert "Dodaj poród" in content
    assert "Dodaj odsadzenie" in content
    assert "Dodaj szczepienie" in content
    assert "Zadania zaplanowane na dziś" in content
    assert "Szczepienia" in content
    assert "Wypełnij" in content
    assert "today-task-dialog-vaccination" in content
    assert "today-task-dialog-ultrasound" in content
    assert 'id="today-task-table"' not in content
    assert 'class="today-task-checkbox"' in content
    assert "Zatwierdź zaznaczone" in content
    assert "USG maciory TODAY-USG" in content
    assert "Szczepienie maciory TODAY-VACCINE" in content
    assert "pregnancy_result_" in content
    assert "Niski stan: TODAY-WHEAT" in content
    assert "dashboard-alert-list" not in content
    assert "Upadek" in content
    assert "2 szt. · Nieokreślone po odsadzeniu" in content
    assert "Sprzedaż netto" in content
    assert "TODAY-SALE" in content
    assert "TODAY-COST" in content
    assert "SECRET-SOW" not in content
    assert "SECRET-SALE" not in content


@pytest.mark.django_db
def test_pre_start_vaccination_is_absent_from_dashboard_and_task_center(
    today_dashboard_client,
):
    today = timezone.localdate()
    farm = today_dashboard_client.farm
    sow = SowModel.objects.create(
        farm=farm,
        ear_tag="HISTORYCZNE-SZCZEPIENIE",
        entry_date=today - timedelta(days=120),
    )
    SowEventModel.objects.create(
        sow=sow,
        event_type="FARROWING",
        event_date=today - timedelta(days=60),
    )
    VaccinationPlanModel.objects.create(
        farm=farm,
        name="Plan od dzisiaj",
        days_after_event=5,
        event_source="FARROWING",
        starts_on=today,
        reminder_days_ahead=7,
    )

    dashboard = today_dashboard_client.get(reverse("modules_home"))
    task_center = TaskCenterService(farm).get_tasks()
    vaccination_tasks = [
        item
        for item in task_center["tabs"]["production"]["items"]
        if item["metadata"].get("kind") == "vaccination"
    ]

    assert dashboard.status_code == 200
    assert (
        "Szczepienie maciory HISTORYCZNE-SZCZEPIENIE"
        not in dashboard.content.decode()
    )
    assert vaccination_tasks == []


@pytest.mark.django_db
def test_mobile_quick_action_links_point_to_expected_views(today_dashboard_client):
    response = today_dashboard_client.get(reverse("modules_home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert f'{reverse("bulk_sow_events")}?rows=1"' in content
    assert f'{reverse("bulk_sow_events")}?rows=1&amp;event_type=FARROWING' in content
    assert f'{reverse("bulk_sow_events")}?rows=1&amp;event_type=WEANING' in content
    assert f'{reverse("bulk_sow_events")}?rows=1&amp;event_type=VACCINATION' in content
    assert f'href="{reverse("report_mortality")}"' in content
    assert f'href="{reverse("add_delivery")}"' in content
    assert f'href="{reverse("add_production")}"' in content
    assert f'href="{reverse("add_sale")}"' in content
    assert f'href="{reverse("add_cost")}"' in content


@pytest.mark.django_db
def test_mobile_dashboard_has_no_full_view_mode_switch(today_dashboard_client):
    response = today_dashboard_client.get(reverse("modules_home"), {"mobile_mode": "full"})
    content = response.content.decode()

    assert response.status_code == 200
    assert 'mobile-dashboard-full' not in content
    assert 'mobile-dashboard-quick' not in content
    assert 'mobile-full-dashboard' not in content
    assert 'mobile-mode-switch' not in content
    assert 'mobile-dashboard-switch' not in content
    assert 'id="today-task-table"' not in content
    assert 'class="mobile-quick-dashboard"' in content
    assert 'class="wide-dashboard"' in content
    assert f'href="{reverse("modules_catalog")}"' in content
    assert 'Pokaż pełny widok' not in content


@pytest.mark.django_db
def test_single_bulk_event_quick_links_prefill_event_type_and_today(today_dashboard_client):
    today = timezone.localdate()
    response = today_dashboard_client.get(reverse("bulk_sow_events"), {
        "rows": "1",
        "event_type": "FARROWING",
    })
    content = response.content.decode()

    assert response.status_code == 200
    assert 'value="FARROWING" selected' in content
    assert f'value="{today.isoformat()}"' in content


@pytest.mark.django_db
def test_today_dashboard_respects_module_visibility_for_actions_and_links(today_dashboard_client):
    settings = get_farm_settings(today_dashboard_client.farm)
    settings.visible_modules = ["tasks", "sows", "settings"]
    settings.nav_modules = ["sows"]
    settings.save(update_fields=["visible_modules", "nav_modules"])

    response = today_dashboard_client.get(reverse("modules_home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Dodaj wpis po numerze kolczyka" in content
    assert "Zgłoś upadek" in content
    assert "Maciory" in content
    assert "Ustawienia" in content
    assert "Dodaj sprzedaż" not in content
    assert "Pełna sprzedaż" not in content


@pytest.mark.django_db
def test_complete_today_tasks_creates_real_sow_events_and_audit_logs(today_dashboard_client):
    today = timezone.localdate()
    farm = today_dashboard_client.farm
    usg_sow = SowModel.objects.create(farm=farm, ear_tag="TODAY-USG-DONE", entry_date=today - timedelta(days=200))
    SowEventModel.objects.create(
        sow=usg_sow,
        event_type="INSEMINATION",
        event_date=today - timedelta(days=35),
    )
    vaccination_sow = SowModel.objects.create(
        farm=farm,
        ear_tag="TODAY-VAC-DONE",
        entry_date=today - timedelta(days=30),
    )
    VaccinationPlanModel.objects.create(
        farm=farm,
        name="Parwo",
        interval_value=1,
        interval_unit="MONTHS",
        schedule_mode="FIXED",
        first_due_date=today,
        reminder_days_ahead=7,
    )
    tasks = TodayDashboardService(farm).completable_tasks_by_id()
    usg_task = next(task for task in tasks.values() if task["metadata"]["kind"] == "ultrasound")
    vaccination_task = next(
        task for task in tasks.values()
        if task["metadata"]["kind"] == "vaccination" and task["metadata"]["sow_id"] == vaccination_sow.id
    )

    response = today_dashboard_client.post(reverse("complete_today_tasks"), {
        "task_ids": [usg_task["task_id"], vaccination_task["task_id"]],
        f"pregnancy_result_{usg_task['task_id']}": "TAK",
        "completion_note": "Bez reakcji po szczepieniu",
    })

    assert response.status_code == 302
    usg_event = SowEventModel.objects.get(sow=usg_sow, event_type="PREGNANCY_CHECK")
    vaccination_event = SowEventModel.objects.get(sow=vaccination_sow, event_type="VACCINATION")
    assert usg_event.event_date == today
    assert usg_event.details == {"result": "TAK"}
    assert vaccination_event.event_date == today
    assert vaccination_event.details["vaccine_name"] == "Parwo"
    assert vaccination_event.details["note"] == "Bez reakcji po szczepieniu"
    assert AuditLogModel.objects.filter(farm=farm, action="CREATE", object_id=str(usg_event.id)).exists()
    assert AuditLogModel.objects.filter(farm=farm, action="CREATE", object_id=str(vaccination_event.id)).exists()
