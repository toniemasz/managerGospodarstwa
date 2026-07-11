from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from costs.models import CostModel
from farms.services.farm_service import get_or_create_user_farm
from feed.models import DeliveryModel, IngredientModel, InventoryMovementModel, ProductionIngredientUsageModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.actions.productions import complete_production, delete_production_with_inventory
from feed.actions.inventory import InventoryActions
from feed.forms import InventoryAdjustmentForm
from feed.services.reconciliation import ProductionReconciliationWorkflow


@pytest.fixture
def inventory_data():
    user = User.objects.create_user(username="inventory")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Jęczmień")
    delivery = DeliveryModel.objects.create(ingredient=ingredient, date=date.today(), quantity_kg=1000, price_per_kg=1)
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="100% jęczmień")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=100)
    return user, farm, ingredient, recipe


def _replace_fifo_deliveries(ingredient):
    for existing in DeliveryModel.objects.filter(ingredient=ingredient):
        InventoryActions(ingredient.farm).remove_delivery(existing)
        existing.delete()
    first_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.20000"),
    )
    second_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.50000"),
    )
    InventoryActions(ingredient.farm).sync_delivery(first_delivery)
    InventoryActions(ingredient.farm).sync_delivery(second_delivery)
    return first_delivery, second_delivery


def _complete_production(farm, recipe, quantity_kg, production_date, user):
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=production_date,
        quantity_kg=Decimal(quantity_kg),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    success, message = complete_production(farm, production.pk, user=user)
    assert success is True, message
    production.refresh_from_db()
    return production


@pytest.mark.django_db
def test_delivery_production_and_repeated_completion_movements(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    assert InventoryActions(farm).balances()[ingredient.pk] == Decimal("1000")
    production = ProductionModel.objects.create(recipe=recipe, date=date.today(), quantity_kg=400, status=ProductionModel.Statuses.STAGE_1_DONE)
    assert complete_production(farm, production.pk, user=user)[0] is True
    assert complete_production(farm, production.pk, user=user)[0] is False
    assert InventoryMovementModel.objects.filter(farm=farm, movement_type="PRODUCTION_USAGE").count() == 1
    assert InventoryActions(farm).balances()[ingredient.pk] == Decimal("600")


@pytest.mark.django_db
def test_completed_production_requires_controlled_delete_and_blocks_direct_edit(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    first_delivery, second_delivery = _replace_fifo_deliveries(ingredient)
    production = _complete_production(farm, recipe, "1200.00", date(2026, 3, 1), user)
    assert production.feed_cost_total == Decimal("1500.00")
    production_cost = CostModel.objects.get(production=production)
    assert production_cost.amount == Decimal("1500.00")
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 2
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_delivery.remaining_quantity_kg == Decimal("0.00")
    assert second_delivery.remaining_quantity_kg == Decimal("800.00")

    production.quantity_kg = Decimal("500.00")
    with pytest.raises(ValidationError):
        production.save()
    production.refresh_from_db()
    with pytest.raises(ValidationError):
        production.delete()

    delete_production_with_inventory(farm, production)
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()
    assert first_delivery.remaining_quantity_kg == Decimal("1000.00")
    assert second_delivery.remaining_quantity_kg == Decimal("1000.00")
    assert not ProductionIngredientUsageModel.objects.exists()
    assert not InventoryMovementModel.objects.filter(movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE).exists()
    assert not CostModel.objects.filter(pk=production_cost.pk).exists()


@pytest.mark.django_db
def test_release_production_does_not_join_nullable_delivery_while_locking(inventory_data):
    _, farm, ingredient, recipe = inventory_data
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 1, 10),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.QUEUED,
    )
    ProductionIngredientUsageModel.objects.create(
        farm=farm,
        production=production,
        ingredient=ingredient,
        delivery=None,
        quantity_kg=Decimal("25.00"),
        unit_price=Decimal("0.00000"),
        cost=Decimal("0.00"),
    )

    with CaptureQueriesContext(connection) as captured:
        InventoryActions(farm).release_production(production)

    usage_selects = [
        query["sql"]
        for query in captured.captured_queries
        if "feed_productioningredientusagemodel" in query["sql"]
        and query["sql"].lstrip().upper().startswith("SELECT")
    ]
    assert usage_selects
    assert "JOIN" not in usage_selects[0].upper()
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()


@pytest.mark.django_db
def test_editing_historical_completed_production_is_blocked(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    first_delivery, second_delivery = _replace_fifo_deliveries(ingredient)
    first_production = _complete_production(farm, recipe, "1200.00", date(2026, 3, 1), user)
    later_production = _complete_production(farm, recipe, "500.00", date(2026, 3, 2), user)

    first_production.quantity_kg = Decimal("500.00")
    with pytest.raises(ValidationError):
        first_production.save()
    later_production.refresh_from_db()
    assert later_production.feed_cost_total == Decimal("750.00")


@pytest.mark.django_db
def test_deleting_historical_completed_production_requires_domain_action(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    first_delivery, second_delivery = _replace_fifo_deliveries(ingredient)
    first_production = _complete_production(farm, recipe, "1200.00", date(2026, 3, 1), user)
    later_production = _complete_production(farm, recipe, "500.00", date(2026, 3, 2), user)

    with pytest.raises(ValidationError):
        first_production.delete()
    assert ProductionModel.objects.filter(pk=first_production.pk).exists()
    assert ProductionModel.objects.filter(pk=later_production.pk).exists()


@pytest.mark.django_db
def test_rebuild_processes_completed_productions_chronologically(inventory_data):
    _, farm, ingredient, recipe = inventory_data
    first_delivery, second_delivery = _replace_fifo_deliveries(ingredient)
    later_production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 3, 2),
        quantity_kg=Decimal("500.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )
    earlier_production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 3, 1),
        quantity_kg=Decimal("1200.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )

    InventoryActions(farm).rebuild()

    earlier_production.refresh_from_db()
    later_production.refresh_from_db()
    first_delivery.refresh_from_db()
    second_delivery.refresh_from_db()

    assert earlier_production.feed_cost_total == Decimal("1500.00")
    assert later_production.feed_cost_total == Decimal("750.00")
    assert first_delivery.remaining_quantity_kg == Decimal("0.00")
    assert second_delivery.remaining_quantity_kg == Decimal("300.00")


@pytest.mark.django_db
def test_rebuild_prefers_legacy_production_usage_movements(inventory_data):
    _, farm, ingredient, recipe = inventory_data
    DeliveryModel.objects.filter(ingredient=ingredient).delete()
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.20000"),
    )
    InventoryActions(farm).sync_delivery(delivery)
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 3, 1),
        quantity_kg=Decimal("1000.00"),
        status=ProductionModel.Statuses.QUEUED,
    )
    ProductionModel.objects.filter(pk=production.pk).update(status=ProductionModel.Statuses.COMPLETED)
    InventoryMovementModel.objects.create(
        farm=farm,
        ingredient=ingredient,
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=production._meta.label,
        source_id=str(production.pk),
        quantity_kg=Decimal("-600.00"),
        unit_price=Decimal("1.20000"),
        movement_date=production.date,
        note="Dane sprzed FIFO - ilość zachowana z ruchu magazynowego",
    )

    InventoryActions(farm).rebuild()

    production.refresh_from_db()
    delivery.refresh_from_db()
    usage = ProductionIngredientUsageModel.objects.get(production=production)
    movement = InventoryMovementModel.objects.get(
        farm=farm,
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=production._meta.label,
        source_id=str(production.pk),
    )

    assert usage.quantity_kg == Decimal("600.00")
    assert movement.quantity_kg == Decimal("-600.00")
    assert production.feed_cost_total == Decimal("720.00")
    assert delivery.remaining_quantity_kg == Decimal("400.00")


@pytest.mark.django_db
def test_future_delivery_blocks_public_completion_but_reconciliation_can_restore_partial_history(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    DeliveryModel.objects.filter(ingredient=ingredient).delete()
    future_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 2, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.20000"),
    )
    InventoryActions(farm).sync_delivery(future_delivery)
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )

    success, message = complete_production(farm, production.pk, user=user)

    assert success is False
    assert "Brakuje rozliczalnych dostaw FIFO" in message
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE

    ProductionModel.objects.filter(pk=production.pk).update(
        status=ProductionModel.Statuses.COMPLETED,
    )
    ProductionReconciliationWorkflow(farm).rebuild()

    production.refresh_from_db()
    future_delivery.refresh_from_db()
    assert production.feed_cost_total == Decimal("0.00")
    assert production.feed_cost_is_partial is True
    assert ingredient.name in production.feed_cost_note
    assert future_delivery.remaining_quantity_kg == Decimal("1000.00")


@pytest.mark.django_db
def test_zero_price_delivery_is_not_used_as_free_fifo_cost(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    DeliveryModel.objects.filter(ingredient=ingredient).delete()
    zero_price_delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("0.00000"),
    )
    InventoryActions(farm).sync_delivery(zero_price_delivery)
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 1, 2),
        quantity_kg=Decimal("500.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )

    success, message = complete_production(farm, production.pk, user=user)

    assert success is False
    assert "Brakuje rozliczalnych dostaw FIFO" in message
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    zero_price_delivery.refresh_from_db()
    assert zero_price_delivery.remaining_quantity_kg == Decimal("1000.00")


@pytest.mark.django_db
def test_rebuild_feed_fifo_command_rolls_back_by_default_and_applies_when_requested(inventory_data):
    user, farm, ingredient, recipe = inventory_data
    delivery = DeliveryModel.objects.get(ingredient=ingredient)
    _complete_production(farm, recipe, "400.00", date.today(), user)
    DeliveryModel.objects.filter(pk=delivery.pk).update(remaining_quantity_kg=Decimal("123.00"))

    dry_run_output = StringIO()
    call_command("rebuild_feed_fifo", "--farm-id", str(farm.id), stdout=dry_run_output)
    delivery.refresh_from_db()

    assert "podgląd" in dry_run_output.getvalue()
    assert delivery.remaining_quantity_kg == Decimal("123.00")

    apply_output = StringIO()
    call_command("rebuild_feed_fifo", "--farm-id", str(farm.id), "--apply", stdout=apply_output)
    delivery.refresh_from_db()

    assert "zapisano" in apply_output.getvalue()
    assert delivery.remaining_quantity_kg == Decimal("600.00")


@pytest.mark.django_db
def test_positive_negative_adjustments_and_cross_farm_isolation(inventory_data):
    user, farm, ingredient, _ = inventory_data
    service = InventoryActions(farm)
    service.adjust(ingredient=ingredient, quantity_kg=100, direction="plus", movement_date=date.today(), reason="remanent", user=user)
    service.adjust(ingredient=ingredient, quantity_kg=50, direction="minus", movement_date=date.today(), reason="ubytek", user=user)
    assert service.balances()[ingredient.pk] == Decimal("1050")
    with pytest.raises(ValidationError):
        service.adjust(ingredient=ingredient, quantity_kg=2000, direction="minus", movement_date=date.today(), reason="błąd", user=user)

    other_user = User.objects.create_user(username="other-inventory")
    other_farm = get_or_create_user_farm(other_user)
    assert not InventoryMovementModel.objects.filter(farm=other_farm).exists()


@pytest.mark.django_db
def test_inventory_adjustment_form_and_view(client, inventory_data):
    user, farm, ingredient, _ = inventory_data
    invalid = InventoryAdjustmentForm({
        "ingredient": ingredient.pk,
        "movement_date": "not-a-date",
        "quantity_kg": "not-a-decimal",
        "direction": "minus",
        "reason": "test",
    }, farm=farm)
    assert not invalid.is_valid()

    client.force_login(user)
    response = client.post(reverse("inventory_adjustment"), {
        "ingredient": ingredient.pk,
        "movement_date": date.today().isoformat(),
        "quantity_kg": "25.50",
        "direction": "plus",
        "reason": "remanent",
    })
    assert response.status_code == 302
    assert InventoryMovementModel.objects.filter(
        farm=farm,
        movement_type=InventoryMovementModel.Types.ADJUSTMENT_POSITIVE,
        quantity_kg=Decimal("25.50"),
    ).exists()
