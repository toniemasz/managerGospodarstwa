import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from farms.services.farm_service import get_or_create_user_farm


NAVIGATION_ROUTES = (
    "modules_home",
    "modules_catalog",
    "dashboard",
    "archived_sows",
    "mortality_list",
    "piglet_transfer_list",
    "bulk_vaccinate",
    "bulk_pregnancy_check",
    "farrowing_panel",
    "bulk_sow_events",
    "general_statistics",
    "vaccination_plans",
    "farm_settings",
    "audit_log",
    "task_center",
    "profitability",
    "farm_statistics",
    "sales_list",
    "add_sale",
    "ingredient_list",
    "add_ingredient",
    "feed_inventory",
    "add_delivery",
    "feed_full_inventory",
    "inventory_adjustment",
    "finished_feed_inventory",
    "create_ready_feed_product",
    "feed_servings",
    "create_feed_serving",
    "feed_recipes",
    "add_recipe",
    "feed_productions",
    "add_production",
    "feed_calculator",
    "cost_list",
    "add_cost",
    "cost_categories",
    "add_cost_category",
)


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_all_static_navigation_tabs_render_without_server_error(client):
    user = get_user_model().objects.create_user(username="navigation-smoke")
    get_or_create_user_farm(user)
    client.force_login(user)
    client.raise_request_exception = False

    failures = []
    for route_name in NAVIGATION_ROUTES:
        response = client.get(reverse(route_name))
        if response.status_code >= 500:
            failures.append((route_name, response.status_code))

    assert failures == []
