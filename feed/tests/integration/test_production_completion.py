from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from farms.services.farm_service import get_or_create_user_farm
from feed.actions.productions import complete_production
from feed.models import (
    DeliveryModel,
    IngredientModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)


@pytest.fixture
def authenticated_farm(client):
    user = User.objects.create_user(username="production-user", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    return client, user, farm


def create_recipe(farm, *, name="Pasza testowa", ingredient_name="Pszenica", stock_kg=None, price="1.00000"):
    ingredient = IngredientModel.objects.create(
        farm=farm,
        name=ingredient_name,
        is_in_bin=True,
    )
    if stock_kg is not None:
        DeliveryModel.objects.create(
            ingredient=ingredient,
            date=date(2026, 7, 1),
            quantity_kg=Decimal(str(stock_kg)),
            price_per_kg=Decimal(price),
        )
    recipe = RecipeModel.objects.create(farm=farm, name=name)
    RecipeItemModel.objects.create(
        recipe=recipe,
        ingredient=ingredient,
        percentage=Decimal("100.00"),
    )
    return recipe, ingredient


def create_production(recipe, *, production_date=date(2026, 7, 8), status=ProductionModel.Statuses.QUEUED, quantity="100.00"):
    return ProductionModel.objects.create(
        date=production_date,
        recipe=recipe,
        quantity_kg=Decimal(quantity),
        status=status,
    )


def completed_local_date(production):
    return timezone.localdate(production.completed_at)


@pytest.mark.django_db
def test_instant_completion_is_atomic_and_uses_planned_date(authenticated_farm):
    client, user, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    planned_date = date(2026, 7, 8)

    response = client.post(reverse("add_production"), {
        "date": planned_date.isoformat(),
        "time": "08:30",
        "recipe": recipe.pk,
        "quantity_kg": "100.00",
        "instant_complete": "on",
    })

    assert response.status_code == 302
    production = ProductionModel.objects.get(recipe=recipe)
    assert production.status == ProductionModel.Statuses.COMPLETED
    assert completed_local_date(production) == planned_date
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 1
    movement_count = InventoryMovementModel.objects.filter(
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=production._meta.label,
        source_id=str(production.pk),
    ).count()
    assert movement_count == 1

    success, _ = complete_production(
        farm,
        production.pk,
        skip_stages=True,
        user=user,
    )
    assert success is False
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 1
    assert InventoryMovementModel.objects.filter(
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=production._meta.label,
        source_id=str(production.pk),
    ).count() == movement_count


@pytest.mark.django_db
def test_failed_instant_completion_leaves_production_queued_without_partial_inventory(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg=None)

    response = client.post(reverse("add_production"), {
        "date": "2026-07-08",
        "time": "08:30",
        "recipe": recipe.pk,
        "quantity_kg": "100.00",
        "instant_complete": "on",
    })

    assert response.status_code == 302
    production = ProductionModel.objects.get(recipe=recipe)
    assert production.status == ProductionModel.Statuses.QUEUED
    assert production.completed_at is None
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    assert not InventoryMovementModel.objects.filter(
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=production._meta.label,
        source_id=str(production.pk),
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "route_name", "expected_route"),
    [
        (ProductionModel.Statuses.STAGE_1_DONE, "process_stage1", "process_stage2"),
        (ProductionModel.Statuses.COMPLETED, "process_stage1", "feed_productions"),
        (ProductionModel.Statuses.QUEUED, "process_stage2", "process_stage1"),
        (ProductionModel.Statuses.COMPLETED, "process_stage2", "feed_productions"),
    ],
)
def test_stage_get_redirects_invalid_statuses_without_server_error(
    authenticated_farm,
    status,
    route_name,
    expected_route,
):
    client, _, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=status)

    response = client.get(reverse(route_name, args=[production.pk]))

    assert response.status_code == 302
    expected_url = (
        reverse(expected_route, args=[production.pk])
        if expected_route != "feed_productions"
        else reverse(expected_route)
    )
    assert response.url == expected_url


@pytest.mark.django_db
def test_stage_post_does_not_change_production_from_wrong_stage(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    after_stage_one = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)
    queued = create_production(recipe, production_date=date(2026, 7, 9))

    stage_one_response = client.post(reverse("process_stage1", args=[after_stage_one.pk]))
    stage_two_response = client.post(reverse("process_stage2", args=[queued.pk]))

    assert stage_one_response.status_code == 302
    assert stage_one_response.url == reverse("process_stage2", args=[after_stage_one.pk])
    assert stage_two_response.status_code == 302
    assert stage_two_response.url == reverse("process_stage1", args=[queued.pk])
    after_stage_one.refresh_from_db()
    queued.refresh_from_db()
    assert after_stage_one.status == ProductionModel.Statuses.STAGE_1_DONE
    assert queued.status == ProductionModel.Statuses.QUEUED


@pytest.mark.django_db
def test_bulk_completion_handles_queued_stage_one_and_duplicate_ids(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="1000.00")
    queued = create_production(recipe, production_date=date(2026, 7, 8))
    stage_one = create_production(
        recipe,
        production_date=date(2026, 7, 9),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )

    response = client.post(reverse("bulk_complete_productions"), {
        "production_ids": [str(stage_one.pk), str(queued.pk), str(queued.pk)],
    })

    assert response.status_code == 302
    queued.refresh_from_db()
    stage_one.refresh_from_db()
    assert queued.status == ProductionModel.Statuses.COMPLETED
    assert stage_one.status == ProductionModel.Statuses.COMPLETED
    assert completed_local_date(queued) == queued.date
    assert completed_local_date(stage_one) == stage_one.date
    assert ProductionIngredientUsageModel.objects.filter(production=queued).count() == 1
    assert ProductionIngredientUsageModel.objects.filter(production=stage_one).count() == 1


@pytest.mark.django_db
def test_bulk_completion_isolated_by_farm(authenticated_farm):
    client, _, farm = authenticated_farm
    own_recipe, _ = create_recipe(farm, name="Własna pasza", stock_kg="500.00")
    own_production = create_production(own_recipe)

    other_user = User.objects.create_user(username="other-production-user", password="password")
    other_farm = get_or_create_user_farm(other_user)
    other_recipe, _ = create_recipe(
        other_farm,
        name="Cudza pasza",
        ingredient_name="Cudza pszenica",
        stock_kg="500.00",
    )
    other_production = create_production(other_recipe)

    response = client.post(reverse("bulk_complete_productions"), {
        "production_ids": [str(own_production.pk), str(other_production.pk)],
    })

    assert response.status_code == 302
    own_production.refresh_from_db()
    other_production.refresh_from_db()
    assert own_production.status == ProductionModel.Statuses.COMPLETED
    assert other_production.status == ProductionModel.Statuses.QUEUED


@pytest.mark.django_db
def test_bulk_completion_continues_after_one_production_fails(authenticated_farm):
    client, _, farm = authenticated_farm
    missing_recipe, _ = create_recipe(farm, name="Brak magazynu", stock_kg=None)
    available_recipe, _ = create_recipe(
        farm,
        name="Dostępna pasza",
        ingredient_name="Jęczmień",
        stock_kg="500.00",
    )
    missing = create_production(missing_recipe, production_date=date(2026, 7, 8))
    available = create_production(available_recipe, production_date=date(2026, 7, 9))

    response = client.post(reverse("bulk_complete_productions"), {
        "production_ids": [str(missing.pk), str(available.pk)],
    })

    assert response.status_code == 302
    missing.refresh_from_db()
    available.refresh_from_db()
    assert missing.status == ProductionModel.Statuses.QUEUED
    assert missing.completed_at is None
    assert available.status == ProductionModel.Statuses.COMPLETED
    assert completed_local_date(available) == available.date


@pytest.mark.django_db
def test_bulk_completion_books_fifo_in_chronological_order(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg="100.00", price="1.00000")
    DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 2),
        quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("2.00000"),
    )
    later = create_production(recipe, production_date=date(2026, 7, 4))
    earlier = create_production(recipe, production_date=date(2026, 7, 3))

    response = client.post(reverse("bulk_complete_productions"), {
        "production_ids": [str(later.pk), str(earlier.pk)],
    })

    assert response.status_code == 302
    earlier.refresh_from_db()
    later.refresh_from_db()
    assert earlier.feed_cost_total == Decimal("100.00")
    assert later.feed_cost_total == Decimal("200.00")


@pytest.mark.django_db
def test_bulk_completion_requires_post_and_selection(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe)

    get_response = client.get(reverse("bulk_complete_productions"))
    empty_response = client.post(reverse("bulk_complete_productions"), {})

    assert get_response.status_code == 405
    assert empty_response.status_code == 302
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.QUEUED
