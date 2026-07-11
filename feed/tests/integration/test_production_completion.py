from datetime import date
from decimal import Decimal

import pytest
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from costs.models import CostModel
from farms.services.farm_service import get_or_create_user_farm
from feed.actions.productions import complete_production
from feed.actions.inventory import InventoryActions
from feed.models import (
    DeliveryModel,
    FeedProductModel,
    FeedServingAllocationModel,
    FeedServingModel,
    FinishedFeedBatchModel,
    IngredientModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)
from farms.models import FarmSettingsModel
from farms.services.settings_service import get_farm_settings


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
        delivery = DeliveryModel.objects.create(
            ingredient=ingredient,
            date=date(2026, 7, 1),
            quantity_kg=Decimal(str(stock_kg)),
            price_per_kg=Decimal(price),
        )
        InventoryActions(farm).sync_delivery(delivery)
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
def test_full_two_stage_http_flow_completes_without_server_error(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg="500.00", price="1.25000")
    production = create_production(recipe, quantity="100.00")

    assert client.get(reverse("process_stage1", args=[production.pk])).status_code == 200
    stage_one = client.post(reverse("process_stage1", args=[production.pk]))
    assert stage_one.status_code == 302
    assert stage_one.url == reverse("process_stage2", args=[production.pk])
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE
    assert client.get(reverse("process_stage2", args=[production.pk])).status_code == 200

    stage_two = client.post(reverse("process_stage2", args=[production.pk]), {})
    assert stage_two.status_code == 302
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.COMPLETED
    assert completed_local_date(production) == production.date
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 1
    assert InventoryMovementModel.objects.filter(source_model=production._meta.label, source_id=str(production.pk), movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE).count() == 1
    assert DeliveryModel.objects.get(ingredient=ingredient).remaining_quantity_kg == Decimal("400.00")
    assert production.feed_cost_total == Decimal("125.00")
    assert production.feed_cost_per_kg == Decimal("1.25000")
    cost = CostModel.objects.get(production=production, farm=farm)
    assert cost.amount == Decimal("125.00")
    assert cost.category.name == "Pasza"
    assert cost.date == production.date
    assert cost.is_paid is True
    batch = FinishedFeedBatchModel.objects.get(production=production)
    assert batch.product.source_type == batch.product.SourceTypes.PRODUCED
    assert batch.initial_quantity_kg == Decimal("100.00")
    assert batch.remaining_quantity_kg == Decimal("0.00")
    assert FeedServingModel.objects.filter(automatic_for_production=production, quantity_kg=Decimal("100.00")).count() == 1


@pytest.mark.django_db
def test_public_production_ui_has_no_force_or_serving_choice_controls(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)

    responses = [
        client.get(reverse("process_stage2", args=[production.pk])),
        client.get(reverse("feed_productions")),
        client.get(reverse("add_production")),
        client.get(reverse("farm_settings")),
    ]
    combined = "\n".join(response.content.decode() for response in responses)
    assert "force_inventory" not in combined
    assert "create_feed_serving" not in combined
    assert "Wymuś zakończenie" not in combined
    assert "mimo braków" not in combined
    assert "pozostać na magazynie" not in combined
    assert "cała wyprodukowana ilość zostanie automatycznie zarejestrowana jako podana" in combined


@pytest.mark.django_db
@pytest.mark.parametrize("legacy_mode", list(FarmSettingsModel.FeedServingModes.values))
def test_legacy_serving_setting_and_post_choice_cannot_disable_automatic_serving(
    authenticated_farm,
    legacy_mode,
):
    client, _, farm = authenticated_farm
    settings = get_farm_settings(farm)
    settings.feed_serving_mode = legacy_mode
    settings.save(update_fields=("feed_serving_mode",))
    recipe, first = create_recipe(farm, stock_kg="500.00", price="1.00000")
    RecipeItemModel.objects.filter(recipe=recipe, ingredient=first).update(percentage=Decimal("50.00"))
    second = IngredientModel.objects.create(farm=farm, name="Soja", is_in_bin=False)
    second_delivery = DeliveryModel.objects.create(ingredient=second, date=date(2026, 7, 1), quantity_kg=Decimal("500.00"), price_per_kg=Decimal("2.00000"))
    InventoryActions(farm).sync_delivery(second_delivery)
    RecipeItemModel.objects.create(recipe=recipe, ingredient=second, percentage=Decimal("50.00"))
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE, quantity="100.00")

    response = client.post(
        reverse("process_stage2", args=[production.pk]),
        {"create_feed_serving": "off", "create_feed_serving_present": "1"},
    )

    assert response.status_code == 302
    batch = FinishedFeedBatchModel.objects.get(production=production)
    assert batch.product.source_type == batch.product.SourceTypes.PRODUCED
    assert batch.remaining_quantity_kg == Decimal("0.00")
    assert FeedServingModel.objects.filter(automatic_for_production=production).count() == 1


@pytest.mark.django_db
def test_completed_production_cost_snapshots_match_fifo_registry_and_batch(authenticated_farm):
    _client, user, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00", price="1.23456")
    production = create_production(
        recipe,
        status=ProductionModel.Statuses.STAGE_1_DONE,
        quantity="100.00",
    )

    success, message = complete_production(
        farm,
        production.pk,
        user=user,
    )

    assert success is True, message
    production.refresh_from_db()
    fifo_total = sum(
        ProductionIngredientUsageModel.objects.filter(production=production)
        .values_list("cost", flat=True),
        Decimal("0.00"),
    )
    cost = CostModel.objects.get(production=production)
    batch = FinishedFeedBatchModel.objects.get(production=production)
    assert fifo_total == production.feed_cost_total == cost.amount == batch.total_cost
    assert production.feed_cost_per_kg == batch.cost_per_kg


@pytest.mark.django_db(transaction=True)
def test_cost_sync_failure_rolls_back_fifo_status_and_batch(authenticated_farm):
    _client, user, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)

    with patch("feed.services.production_completion.sync_production_cost", side_effect=RuntimeError("awaria rejestru")):
        with pytest.raises(RuntimeError, match="awaria rejestru"):
            complete_production(farm, production.pk, user=user)

    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE
    assert DeliveryModel.objects.get(ingredient=ingredient).remaining_quantity_kg == Decimal("500.00")
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    assert not CostModel.objects.filter(production=production).exists()
    assert not FinishedFeedBatchModel.objects.filter(production=production).exists()


@pytest.mark.django_db(transaction=True)
def test_batch_creation_failure_rolls_back_fifo_and_cost(authenticated_farm):
    _client, user, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)

    with patch(
        "feed.services.production_completion.create_finished_feed_batch_for_production",
        side_effect=RuntimeError("awaria partii"),
    ):
        with pytest.raises(RuntimeError, match="awaria partii"):
            complete_production(farm, production.pk, user=user)

    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE
    assert DeliveryModel.objects.get(ingredient=ingredient).remaining_quantity_kg == Decimal("500.00")
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    assert not CostModel.objects.filter(production=production).exists()


@pytest.mark.django_db
def test_stage_two_auto_mode_creates_exactly_one_feed_serving(authenticated_farm):
    client, _, farm = authenticated_farm
    settings = get_farm_settings(farm)
    settings.feed_serving_mode = FarmSettingsModel.FeedServingModes.AUTO_FULL_PRODUCTION
    settings.save(update_fields=("feed_serving_mode",))
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)

    response = client.post(reverse("process_stage2", args=[production.pk]), {"create_feed_serving": "on"})
    assert response.status_code == 302
    batch = FinishedFeedBatchModel.objects.get(production=production)
    serving = FeedServingModel.objects.get(automatic_for_production=production)
    assert serving.quantity_kg == production.quantity_kg
    assert FeedServingAllocationModel.objects.filter(serving=serving, batch=batch).count() == 1
    batch.refresh_from_db()
    assert batch.remaining_quantity_kg == Decimal("0.00")

    client.post(reverse("process_stage2", args=[production.pk]), {"create_feed_serving": "on"})
    assert FinishedFeedBatchModel.objects.filter(production=production).count() == 1
    assert FeedServingModel.objects.filter(automatic_for_production=production).count() == 1


@pytest.mark.django_db
def test_automatic_serving_uses_only_batch_created_for_that_production(authenticated_farm):
    _client, user, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    product = FeedProductModel.objects.create(
        farm=farm,
        name=recipe.name,
        source_type=FeedProductModel.SourceTypes.PRODUCED,
        recipe=recipe,
    )
    historical_production = create_production(
        recipe,
        production_date=date(2026, 7, 7),
        status=ProductionModel.Statuses.COMPLETED,
        quantity="25.00",
    )
    historical_batch = FinishedFeedBatchModel.objects.create(
        farm=farm,
        product=product,
        batch_date=historical_production.date,
        initial_quantity_kg=Decimal("25.00"),
        remaining_quantity_kg=Decimal("25.00"),
        cost_per_kg=Decimal("1.00000"),
        total_cost=Decimal("25.00"),
        production=historical_production,
    )
    production = create_production(
        recipe,
        production_date=date(2026, 7, 8),
        status=ProductionModel.Statuses.STAGE_1_DONE,
        quantity="100.00",
    )

    success, message = complete_production(farm, production.pk, user=user)

    assert success, message
    serving = FeedServingModel.objects.get(automatic_for_production=production)
    new_batch = FinishedFeedBatchModel.objects.get(production=production)
    assert list(serving.allocations.values_list("batch_id", flat=True)) == [new_batch.pk]
    historical_batch.refresh_from_db()
    new_batch.refresh_from_db()
    assert historical_batch.remaining_quantity_kg == Decimal("25.00")
    assert new_batch.remaining_quantity_kg == Decimal("0.00")


@pytest.mark.django_db
def test_automatic_fifo_cost_cannot_be_edited_or_deleted_manually(authenticated_farm):
    client, user, farm = authenticated_farm
    recipe, _ = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)
    success, message = complete_production(farm, production.pk, user=user)
    assert success is True, message
    cost = CostModel.objects.get(production=production)

    edit_response = client.get(reverse("edit_cost", args=[cost.pk]))
    delete_response = client.post(reverse("delete_cost", args=[cost.pk]))

    assert edit_response.status_code == 302
    assert delete_response.status_code == 302
    production.refresh_from_db()
    cost.refresh_from_db()
    assert cost.amount == production.feed_cost_total


@pytest.mark.django_db
def test_stage_two_uses_automatic_farm_setting_when_post_has_no_explicit_choice(authenticated_farm):
    client, _, farm = authenticated_farm
    settings = get_farm_settings(farm)
    settings.feed_serving_mode = FarmSettingsModel.FeedServingModes.AUTO_FULL_PRODUCTION
    settings.save(update_fields=("feed_serving_mode",))
    recipe, first = create_recipe(farm, stock_kg="500.00")
    RecipeItemModel.objects.filter(recipe=recipe, ingredient=first).update(percentage=Decimal("50.00"))
    second = IngredientModel.objects.create(farm=farm, name="Jęczmień", is_in_bin=True)
    second_delivery = DeliveryModel.objects.create(
        ingredient=second,
        date=date(2026, 7, 1),
        quantity_kg=Decimal("500.00"),
        price_per_kg=Decimal("1.00000"),
    )
    InventoryActions(farm).sync_delivery(second_delivery)
    RecipeItemModel.objects.create(recipe=recipe, ingredient=second, percentage=Decimal("50.00"))
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)

    response = client.post(reverse("process_stage2", args=[production.pk]), {})

    assert response.status_code == 302
    serving = FeedServingModel.objects.get(automatic_for_production=production)
    assert serving.quantity_kg == production.quantity_kg
    assert serving.time == production.time
    assert FinishedFeedBatchModel.objects.get(production=production).remaining_quantity_kg == Decimal("0.00")


@pytest.mark.django_db(transaction=True)
def test_future_delivery_is_rejected_before_fifo_booking(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg=None)
    future_delivery = DeliveryModel.objects.create(ingredient=ingredient, date=date(2026, 7, 9), quantity_kg=Decimal("500.00"), price_per_kg=Decimal("1.0"))
    InventoryActions(farm).sync_delivery(future_delivery)
    production = create_production(recipe, production_date=date(2026, 7, 8), status=ProductionModel.Statuses.STAGE_1_DONE)

    response = client.post(reverse("process_stage2", args=[production.pk]), {
        "force_inventory": "on",
        "create_feed_serving": "off",
        "create_feed_serving_present": "1",
    })
    assert response.status_code == 302
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE
    assert production.completed_at is None
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    assert not InventoryMovementModel.objects.filter(
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=production._meta.label,
        source_id=str(production.pk),
    ).exists()
    assert not CostModel.objects.filter(production=production).exists()
    assert not FinishedFeedBatchModel.objects.filter(production=production).exists()
    assert not FeedServingModel.objects.filter(automatic_for_production=production).exists()


@pytest.mark.django_db(transaction=True)
def test_stage_two_auto_serving_failure_rolls_back_entire_completion(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg="500.00")
    production = create_production(recipe, status=ProductionModel.Statuses.STAGE_1_DONE)

    with patch("feed.services.production_completion.create_feed_serving", side_effect=ValidationError("Błąd podania")):
        response = client.post(reverse("process_stage2", args=[production.pk]), {"create_feed_serving": "on"})

    assert response.status_code == 302
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE
    assert production.completed_at is None
    assert not FinishedFeedBatchModel.objects.filter(production=production).exists()
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    assert not InventoryMovementModel.objects.filter(source_model=production._meta.label, source_id=str(production.pk), movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE).exists()
    assert DeliveryModel.objects.get(ingredient=ingredient).remaining_quantity_kg == Decimal("500.00")


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
    assert FeedServingModel.objects.filter(automatic_for_production__in=[queued, stage_one]).count() == 2
    assert FinishedFeedBatchModel.objects.filter(
        production__in=[queued, stage_one], remaining_quantity_kg=Decimal("0.00"),
    ).count() == 2


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
        "force_inventory": "on",
    })

    assert response.status_code == 302
    missing.refresh_from_db()
    available.refresh_from_db()
    assert missing.status == ProductionModel.Statuses.QUEUED
    assert missing.completed_at is None
    assert not ProductionIngredientUsageModel.objects.filter(production=missing).exists()
    assert not CostModel.objects.filter(production=missing).exists()
    assert not FinishedFeedBatchModel.objects.filter(production=missing).exists()
    assert not FeedServingModel.objects.filter(automatic_for_production=missing).exists()
    assert available.status == ProductionModel.Statuses.COMPLETED
    assert completed_local_date(available) == available.date
    assert FeedServingModel.objects.filter(automatic_for_production=available).count() == 1


@pytest.mark.django_db
def test_bulk_completion_books_fifo_in_chronological_order(authenticated_farm):
    client, _, farm = authenticated_farm
    recipe, ingredient = create_recipe(farm, stock_kg="100.00", price="1.00000")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 2),
        quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("2.00000"),
    )
    InventoryActions(farm).sync_delivery(delivery)
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
