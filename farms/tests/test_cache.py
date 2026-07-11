from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from common.cache import (
    cached_farm_value,
    farm_cache_key,
    safe_cache_get,
    safe_cache_set,
)
from farms.services.farm_service import get_or_create_user_farm
from farms.services.task_center import TaskCenterService
from feed.actions.deliveries import create_delivery
from feed.forms import DeliveryForm
from feed.models import IngredientModel
from feed.selectors import inventory as inventory_selector
from sows.actions.events import SowEventActions
from sows.models import SowModel
from managerGospodarstwa.settings import _cache_backend_config


LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-manager-gospodarstwa-cache",
        "KEY_PREFIX": "test-manager-gospodarstwa",
    },
}


@pytest.fixture
def farm_user():
    user = get_user_model().objects.create_user(username="cache-user")
    return user, get_or_create_user_farm(user)


def _empty_task_result():
    tabs = {
        "production": {
            "key": "production",
            "title": "Produkcja",
            "count": 0,
            "sections": [],
            "items": [],
            "empty_message": "",
            "urgent_count": 0,
        },
    }
    return {
        "tabs": tabs,
        "tab_list": list(tabs.values()),
        "task_count": 0,
        "low_stock": [],
        "unsettled_sales": [],
    }


def test_cache_backend_config_uses_dummy_for_tests_and_locmem_without_cache_url():
    test_config = _cache_backend_config(cache_url="", testing=True)
    local_config = _cache_backend_config(cache_url="", testing=False)
    invalid_url_config = _cache_backend_config(cache_url="postgres://db", testing=False)
    redis_config = _cache_backend_config(cache_url="redis://localhost:6379/1", testing=False)

    assert test_config["BACKEND"] == "django.core.cache.backends.dummy.DummyCache"
    assert local_config["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"
    assert invalid_url_config["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache"
    assert redis_config["BACKEND"] == "django.core.cache.backends.redis.RedisCache"
    assert "LOCATION" not in test_config


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db
def test_farm_cache_key_contains_schema_farm_group_version_and_params(farm_user):
    _, farm = farm_user
    cache.clear()

    key = farm_cache_key(farm, "inventory", date(2026, 7, 10), {"status": "open"})

    assert key.startswith("v1:")
    assert f":farm:{farm.id}:inventory:" in key
    assert ":gv:1:" in key
    assert "2026-07-10" in key
    assert "status" in key


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db
def test_cached_value_survives_cache_backend_errors(farm_user):
    _, farm = farm_user

    with (
        mock.patch("farms.services.cache.cache.get", side_effect=RuntimeError("cache get failed")),
        mock.patch("farms.services.cache.cache.set", side_effect=RuntimeError("cache set failed")),
    ):
        result = cached_farm_value(
            farm,
            "task_center",
            (),
            timeout=60,
            builder=lambda: {"ok": True},
        )

    assert result == {"ok": True}


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db
def test_task_center_service_reuses_farm_cache(farm_user):
    _, farm = farm_user
    cache.clear()

    with mock.patch.object(
        TaskCenterService,
        "_build_tasks",
        autospec=True,
        return_value=_empty_task_result(),
    ) as build_tasks:
        first_result = TaskCenterService(farm).get_tasks()
        second_result = TaskCenterService(farm).get_tasks()

    assert first_result == second_result
    assert build_tasks.call_count == 1


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db
def test_inventory_dashboard_reuses_farm_cache(farm_user):
    _, farm = farm_user
    cache.clear()
    IngredientModel.objects.create(farm=farm, name="Pszenica")

    with mock.patch(
        "feed.selectors.inventory.movement_totals",
        wraps=inventory_selector.movement_totals,
    ) as movement_totals:
        first_result = inventory_selector.inventory_dashboard(farm)
        second_result = inventory_selector.inventory_dashboard(farm)

    assert first_result["total_inventory_kg"] == Decimal("0.00")
    assert second_result["total_inventory_kg"] == Decimal("0.00")
    assert movement_totals.call_count == 1


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db(transaction=True)
def test_delivery_creation_invalidates_inventory_cache(farm_user):
    user, farm = farm_user
    cache.clear()
    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica")

    initial = inventory_selector.inventory_dashboard(farm)
    assert initial["total_inventory_kg"] == Decimal("0.00")

    form = DeliveryForm(
        data={
            "date": date(2026, 7, 10),
            "ingredient": ingredient.id,
            "quantity_kg": "120.00",
            "price_per_kg": "1.23000",
        },
        farm=farm,
    )
    assert form.is_valid() is True

    create_delivery(form, farm=farm, user=user)

    refreshed = inventory_selector.inventory_dashboard(farm)
    assert refreshed["total_inventory_kg"] == Decimal("120.00")


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db(transaction=True)
def test_sow_event_invalidates_task_and_dashboard_cache_groups(farm_user):
    _, farm = farm_user
    cache.clear()
    sow = SowModel.objects.create(farm=farm, ear_tag="CACHE-1")
    today = timezone.localdate()

    task_key_before = farm_cache_key(farm, "task_center", today)
    dashboard_key_before = farm_cache_key(farm, "dashboard")
    today_dashboard_key_before = farm_cache_key(farm, "today_dashboard", today)
    safe_cache_set(task_key_before, {"cached": True}, timeout=60)

    SowEventActions(farm=farm).create_event(
        sow=sow,
        sow_status="IDLE",
        data={
            "event_type": "INSEMINATION",
            "event_date": today,
            "technician": "Jan",
        },
    )

    assert safe_cache_get(task_key_before) == {"cached": True}
    assert farm_cache_key(farm, "task_center", today) != task_key_before
    assert farm_cache_key(farm, "dashboard") != dashboard_key_before
    assert farm_cache_key(farm, "today_dashboard", today) != today_dashboard_key_before
