import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from farms.module_registry import MODULE_DEFINITIONS, MODULE_GROUPS
from farms.services.farm_service import get_or_create_user_farm
from farms.services.module_navigation import ModuleNavigationService
from farms.services.settings_service import get_farm_settings


@pytest.fixture
def catalog_client(client):
    user = get_user_model().objects.create_user(username="catalog-owner", password="test")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    client.farm = farm
    return client


@pytest.mark.django_db
def test_modules_catalog_renders_only_groups_and_primary_modules(catalog_client):
    response = catalog_client.get(reverse("modules_catalog"))
    content = response.content.decode()

    assert response.status_code == 200
    assert all(title in content for _key, title in MODULE_GROUPS)
    assert all(definition["title"] in content for definition in MODULE_DEFINITIONS)
    assert "module-catalog-actions" not in content
    assert "module-action-group" not in content
    assert "module-action-subnav" not in content
    assert "Przypięty do nawigacji" not in content
    assert "Najważniejsze alerty produkcyjne, magazynowe i finansowe." not in content


@pytest.mark.django_db
def test_catalog_modules_no_longer_expose_catalog_links(catalog_client):
    modules = ModuleNavigationService(catalog_client.farm).all_modules()
    assert all("catalog_links" not in module for module in modules)


@pytest.mark.django_db
def test_pin_buttons_expose_state_and_settings_have_no_pin(catalog_client):
    settings = get_farm_settings(catalog_client.farm)
    settings.nav_modules = ["sows"]
    settings.save(update_fields=["nav_modules"])

    content = catalog_client.get(reverse("modules_catalog")).content.decode()

    assert 'value="sows"' in content
    assert re.search(r'class="module-pin-button is-pinned"[^>]*aria-pressed="true"', content, re.S)
    assert re.search(r'class="module-pin-button(?! is-pinned)"[^>]*aria-pressed="false"', content, re.S)
    assert 'aria-label="Odepnij moduł Maciory od paska nawigacji"' in content
    assert 'aria-label="Przypnij moduł Statystyki do paska nawigacji"' in content
    assert content.count('class="module-pin-form"') == len(MODULE_DEFINITIONS) - 1


@pytest.mark.django_db
def test_hidden_module_has_disabled_pin_and_settings_link(catalog_client):
    settings = get_farm_settings(catalog_client.farm)
    settings.visible_modules = ["tasks", "settings"]
    settings.nav_modules = ["tasks"]
    settings.save(update_fields=["visible_modules", "nav_modules"])

    content = catalog_client.get(reverse("modules_catalog")).content.decode()

    assert re.search(r'value="sows".*?<button[^>]*disabled', content, re.S)
    assert 'title="Najpierw włącz moduł w ustawieniach"' in content
    assert f'{reverse("farm_settings")}#settings-modules' in content


@pytest.mark.django_db
def test_pin_and_unpin_use_the_same_nav_modules_setting(catalog_client):
    settings = get_farm_settings(catalog_client.farm)
    settings.nav_modules = []
    settings.save(update_fields=["nav_modules"])

    pin = catalog_client.post(reverse("set_module_pin"), {"module_key": "sows", "is_pinned": "on"})
    assert pin.status_code == 302
    assert pin.url == reverse("modules_catalog")
    settings.refresh_from_db()
    assert "sows" in settings.nav_modules

    unpin = catalog_client.post(reverse("set_module_pin"), {"module_key": "sows"})
    assert unpin.status_code == 302
    settings.refresh_from_db()
    assert "sows" not in settings.nav_modules


@pytest.mark.django_db
def test_pin_endpoint_changes_only_current_farm(catalog_client):
    other_user = get_user_model().objects.create_user(username="catalog-other", password="test")
    other_settings = get_farm_settings(get_or_create_user_farm(other_user))
    original_other_nav = list(other_settings.nav_modules)

    response = catalog_client.post(reverse("set_module_pin"), {"module_key": "sows"})

    assert response.status_code == 302
    other_settings.refresh_from_db()
    assert other_settings.nav_modules == original_other_nav


@pytest.mark.django_db
def test_pin_endpoint_accepts_only_post(catalog_client):
    assert catalog_client.get(reverse("set_module_pin")).status_code == 405


@pytest.mark.django_db
def test_mobile_navigation_has_stable_order_and_respects_pinned_modules(catalog_client):
    settings = get_farm_settings(catalog_client.farm)
    settings.visible_modules = ["tasks", "sows", "inventory", "sales", "settings"]
    settings.nav_modules = ["tasks", "sows", "sales", "inventory"]
    settings.save(update_fields=["visible_modules", "nav_modules"])

    keys_by_page = []
    for active_url in ("dashboard", "sales_list", "feed_inventory"):
        service = ModuleNavigationService(catalog_client.farm, active_url)
        mobile = service.mobile_modules()
        keys_by_page.append([module["key"] for module in mobile])

    assert keys_by_page == [
        ["tasks", "sows", "inventory"],
        ["tasks", "sows", "inventory"],
        ["tasks", "sows", "inventory"],
    ]


@pytest.mark.django_db
def test_mobile_navigation_has_no_duplicates_and_at_most_three_modules(catalog_client):
    settings = get_farm_settings(catalog_client.farm)
    settings.nav_modules = ["tasks", "sows", "inventory", "sales", "costs"]
    settings.save(update_fields=["nav_modules"])

    mobile = ModuleNavigationService(catalog_client.farm, "sales_list").mobile_modules()
    keys = [module["key"] for module in mobile]

    assert len(keys) <= 3
    assert len(keys) == len(set(keys))


@pytest.mark.django_db
def test_mobile_catalog_is_active_for_module_outside_bottom_bar(catalog_client):
    settings = get_farm_settings(catalog_client.farm)
    settings.nav_modules = ["tasks", "sows", "inventory"]
    settings.save(update_fields=["nav_modules"])
    service = ModuleNavigationService(catalog_client.farm, "sales_list")
    modules = service.modules()
    mobile = service.mobile_modules(modules)

    assert service.is_mobile_catalog_active(modules, mobile) is True
    assert [module["key"] for module in mobile] == ["tasks", "sows", "inventory"]


@pytest.mark.django_db
def test_mobile_search_uses_existing_global_search_endpoint(catalog_client):
    content = catalog_client.get(reverse("modules_home")).content.decode()

    assert 'data-mobile-search' in content
    assert f'action="{reverse("global_search")}"' in content
    assert 'aria-label="Wyszukiwarka"' in content
