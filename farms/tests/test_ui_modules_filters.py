from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from farms.module_registry import MODULE_KEYS
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from sales.models import PigSaleModel
from sows.models import SowEventModel, SowModel


@pytest.fixture
def ui_client(client):
    user = get_user_model().objects.create_user(username="ui-owner", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    client.farm = farm
    return client


def _settings_payload(**overrides):
    data = {
        "farm_name": "Gospodarstwo UI",
        "interface_scale": "standard",
        "theme": "light",
        "font_scale": "100",
        "pregnancy_check_after_days": 30,
        "gestation_days": 114,
        "farrowing_alert_days_ahead": 7,
        "vaccination_alert_days_ahead": 7,
        "default_production_quantity_kg": "2000.00",
        "allow_farrowing_without_pregnancy_check": "on",
        "ask_before_auto_pregnancy_check": "on",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_module_visibility_defaults_save_and_settings_stay_available(ui_client):
    settings = get_farm_settings(ui_client.farm)
    assert settings.visible_modules == list(MODULE_KEYS)

    response = ui_client.post(
        reverse("farm_settings"),
        _settings_payload(show_tasks="on", show_sows="on", nav_sows="on"),
    )
    assert response.status_code == 302
    settings.refresh_from_db()
    assert settings.visible_modules == ["tasks", "sows", "settings"]
    assert settings.nav_modules == ["sows"]

    home = ui_client.get(reverse("modules_home"))
    home_content = home.content.decode()
    assert "Zadania" in home_content
    assert "Maciory" in home_content
    assert "Sprzedaż" not in home_content
    assert "Ustawienia" in home_content

    direct_sale = ui_client.get(reverse("sales_list"))
    assert direct_sale.status_code == 200
    assert [item["key"] for item in direct_sale.context["ui_modules"]] == ["tasks", "sows", "settings"]
    assert [item["key"] for item in direct_sale.context["ui_primary_modules"]] == ["sows"]
    assert reverse("farm_settings") in direct_sale.content.decode()


@pytest.mark.django_db
def test_task_center_uses_short_previews_and_links_to_full_panels(ui_client):
    today = timezone.localdate()
    for index in range(6):
        sow = SowModel.objects.create(
            farm=ui_client.farm,
            ear_tag=f"SHORT-{index + 1}",
            entry_date=today - timedelta(days=200),
        )
        SowEventModel.objects.create(
            sow=sow,
            event_type="INSEMINATION",
            event_date=today - timedelta(days=35),
        )

    response = ui_client.get(reverse("task_center"), {"tab": "production"})
    content = response.content.decode()
    assert response.status_code == 200
    preview_titles = [
        item["title"]
        for section in response.context["active_tab_data"]["sections"]
        for item in section["preview_items"]
    ]
    assert "SHORT-1" in content and "SHORT-3" in content
    assert all("SHORT-4" not in title and "SHORT-5" not in title and "SHORT-6" not in title for title in preview_titles)
    assert "+ 3 więcej" in content
    assert reverse("bulk_pregnancy_check") in content
    assert reverse("bulk_vaccinate") in content
    assert reverse("farrowing_panel") in content
    assert "task-list" not in content


@pytest.mark.django_db
def test_farrowing_panel_is_farm_scoped_and_links_to_prefilled_event(ui_client):
    today = timezone.localdate()
    settings = get_farm_settings(ui_client.farm)
    own_sow = SowModel.objects.create(farm=ui_client.farm, ear_tag="OWN-FARROW", entry_date=today - timedelta(days=300))
    insemination = today - timedelta(days=settings.gestation_days - 3)
    SowEventModel.objects.create(sow=own_sow, event_type="INSEMINATION", event_date=insemination)
    SowEventModel.objects.create(sow=own_sow, event_type="PREGNANCY_CHECK", event_date=insemination + timedelta(days=30), details={"result": "TAK"})

    other_user = get_user_model().objects.create_user(username="ui-other")
    other_farm = get_or_create_user_farm(other_user)
    other_sow = SowModel.objects.create(farm=other_farm, ear_tag="OTHER-FARROW", entry_date=today - timedelta(days=300))
    SowEventModel.objects.create(sow=other_sow, event_type="INSEMINATION", event_date=insemination)

    response = ui_client.get(reverse("farrowing_panel"))
    content = response.content.decode()
    assert response.status_code == 200
    assert "OWN-FARROW" in content
    assert "OTHER-FARROW" not in content
    assert f"{reverse('add_event', args=[own_sow.pk])}?event_type=FARROWING" in content


@pytest.mark.django_db
def test_filters_render_as_disclosure_with_active_chips(ui_client):
    PigSaleModel.objects.create(farm=ui_client.farm, sale_date=date(2025, 2, 1), document_number="FILTER/1")
    response = ui_client.get(reverse("sales_list"), {"year": "2025"})
    content = response.content.decode()
    assert response.status_code == 200
    assert '<details class="filter-disclosure" open>' in content
    assert "Rok: 2025" in content
    assert "Wyczyść filtry" in content

    plain = ui_client.get(reverse("sales_list"))
    assert '<details class="filter-disclosure">' in plain.content.decode()


@pytest.mark.django_db
def test_settings_visibility_section_is_grouped(ui_client):
    response = ui_client.get(reverse("farm_settings"))
    content = response.content.decode()
    assert all(label in content for label in ["Widoczność modułów", "Produkcja", "Pasza i magazyn", "Finanse", "System"])
    assert "Ustawienia zawsze widoczne" in content
    assert "Przypięty w menu" in content
    assert "Gęstość interfejsu" in content
    assert "Motyw" in content
    assert "Rozmiar tekstu" in content
    assert 'type="range"' in content
    assert 'min="80"' in content
    assert 'max="150"' in content
    assert "Własna wartość" in content
    assert "Masz niezapisane zmiany" in content
    assert 'data-font-scale-preset="140"' in content
    assert 'data-settings-save' in content


@pytest.mark.django_db
def test_settings_appearance_choices_are_applied_to_page_shell(ui_client):
    settings = get_farm_settings(ui_client.farm)
    settings.interface_scale = "compact"
    settings.theme = "dark"
    settings.font_scale = 137
    settings.save(update_fields=["interface_scale", "theme", "font_scale"])

    response = ui_client.get(reverse("farm_settings"))
    content = response.content.decode()

    assert response.status_code == 200
    assert 'class="theme-dark ui-density-compact"' in content
    assert "--user-font-scale: 1.37;" in content


@pytest.mark.django_db
@pytest.mark.parametrize("font_scale", ["79", "151"])
def test_settings_font_scale_is_limited_to_safe_range(ui_client, font_scale):
    response = ui_client.post(reverse("farm_settings"), _settings_payload(font_scale=font_scale))

    assert response.status_code == 200
    assert "font_scale" in response.context["form"].errors


@pytest.mark.django_db
def test_global_search_finds_owned_records_modules_and_handles_short_query(ui_client):
    SowModel.objects.create(farm=ui_client.farm, ear_tag="SEARCH-SOW")
    PigSaleModel.objects.create(farm=ui_client.farm, document_number="FV-SEARCH", quantity=12)

    other_user = get_user_model().objects.create_user(username="ui-search-other")
    other_farm = get_or_create_user_farm(other_user)
    SowModel.objects.create(farm=other_farm, ear_tag="SECRET-SOW")

    response = ui_client.get(reverse("global_search"), {"q": "search"})
    content = response.content.decode()
    assert response.status_code == 200
    assert "SEARCH-SOW" in content
    assert "FV-SEARCH" in content
    assert "SECRET-SOW" not in content

    module_response = ui_client.get(reverse("global_search"), {"q": "maciory"})
    module_content = module_response.content.decode()
    assert module_response.status_code == 200
    assert "Moduły" in module_content
    assert "Maciory" in module_content

    short = ui_client.get(reverse("global_search"), {"q": "s"})
    assert short.status_code == 200
    assert "Wpisz co najmniej 2 znaki" in short.content.decode()
