from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.db.models import Sum

from costs.models import CostModel
from farms.services.farm_service import get_or_create_user_farm
from feed.models import (
    DeliveryModel,
    FeedProductModel,
    FeedServingAllocationModel,
    FeedServingModel,
    FinishedFeedBatchModel,
    IngredientModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)
from feed.selectors.production_costs import ProductionCostSelector


@pytest.mark.django_db(transaction=True)
def test_historical_migration_classifies_recipes_serves_ready_feed_and_preserves_cost_once():
    user = User.objects.create_user(username="history-migration")
    farm = get_or_create_user_farm(user)
    ready_ingredient = IngredientModel.objects.create(farm=farm, name="Bebito surowiec")
    grain = IngredientModel.objects.create(farm=farm, name="Pszenica")
    supplement = IngredientModel.objects.create(farm=farm, name="Premiks")
    for ingredient, price in ((ready_ingredient, "2.00000"), (grain, "1.00000"), (supplement, "3.00000")):
        DeliveryModel.objects.create(
            ingredient=ingredient,
            date=date(2026, 1, 1),
            quantity_kg=Decimal("1000.00"),
            price_per_kg=Decimal(price),
        )

    ready_recipe = RecipeModel.objects.create(farm=farm, name="Bebito")
    RecipeItemModel.objects.create(recipe=ready_recipe, ingredient=ready_ingredient, percentage=Decimal("100.00"))
    mixed_recipe = RecipeModel.objects.create(farm=farm, name="Tucznik")
    RecipeItemModel.objects.create(recipe=mixed_recipe, ingredient=grain, percentage=Decimal("50.00"))
    RecipeItemModel.objects.create(recipe=mixed_recipe, ingredient=supplement, percentage=Decimal("50.00"))

    ready_production = ProductionModel.objects.create(
        recipe=ready_recipe, date=date(2026, 1, 2), quantity_kg=Decimal("100.00"), status=ProductionModel.Statuses.COMPLETED,
    )
    mixed_production = ProductionModel.objects.create(
        recipe=mixed_recipe, date=date(2026, 1, 3), quantity_kg=Decimal("100.00"), status=ProductionModel.Statuses.COMPLETED,
    )

    migration = import_module("feed.migrations.0008_backfill_finished_feed_history")
    migration.backfill_finished_feed_history(django_apps, None)
    migration.backfill_finished_feed_history(django_apps, None)

    ready_production.refresh_from_db(); mixed_production.refresh_from_db()
    assert ready_production.feed_cost_total == Decimal("200.00")
    assert mixed_production.feed_cost_total == Decimal("200.00")
    assert ready_production.completion_feed_serving_mode == "AUTO_FULL_PRODUCTION"
    assert mixed_production.completion_feed_serving_mode == "MANUAL"

    ready_product = FeedProductModel.objects.get(recipe=ready_recipe)
    mixed_product = FeedProductModel.objects.get(recipe=mixed_recipe)
    assert ready_product.source_type == FeedProductModel.SourceTypes.PURCHASED_READY
    assert mixed_product.source_type == FeedProductModel.SourceTypes.PRODUCED
    ready_batch = FinishedFeedBatchModel.objects.get(production=ready_production)
    mixed_batch = FinishedFeedBatchModel.objects.get(production=mixed_production)
    assert ready_batch.remaining_quantity_kg == Decimal("0.00")
    assert mixed_batch.remaining_quantity_kg == Decimal("100.00")
    serving = FeedServingModel.objects.get(automatic_for_production=ready_production)
    assert serving.total_cost == Decimal("200.00")
    assert FeedServingAllocationModel.objects.filter(serving=serving, batch=ready_batch).count() == 1
    assert not FeedServingModel.objects.filter(automatic_for_production=mixed_production).exists()
    assert FinishedFeedBatchModel.objects.filter(production__in=[ready_production, mixed_production]).count() == 2
    assert FeedServingModel.objects.filter(automatic_for_production=ready_production).count() == 1
    assert CostModel.objects.filter(farm=farm, production__in=[ready_production, mixed_production]).count() == 2
    assert CostModel.objects.filter(farm=farm).aggregate(total=Sum("amount"))["total"] == Decimal("400.00")
    assert ProductionCostSelector(farm).calculate()["total_cost"] == Decimal("400.00")


@pytest.mark.django_db(transaction=True)
def test_historical_migration_marks_missing_prices_as_partial_instead_of_inventing_cost():
    user = User.objects.create_user(username="history-missing-price")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Bez ceny")
    recipe = RecipeModel.objects.create(farm=farm, name="Niepełna")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal("100.00"))
    production = ProductionModel.objects.create(
        recipe=recipe, date=date(2025, 1, 1), quantity_kg=Decimal("100.00"), status=ProductionModel.Statuses.QUEUED,
    )
    ProductionModel.objects.filter(pk=production.pk).update(status=ProductionModel.Statuses.COMPLETED)

    migration = import_module("feed.migrations.0008_backfill_finished_feed_history")
    migration.backfill_finished_feed_history(django_apps, None)

    production.refresh_from_db()
    assert production.feed_cost_total == Decimal("0.00")
    assert production.feed_cost_is_partial is True
    assert "brak ceny" in production.feed_cost_note.casefold()
    assert FinishedFeedBatchModel.objects.get(production=production).cost_is_partial is True


@pytest.mark.django_db(transaction=True)
def test_new_backfill_adds_missing_serving_for_historical_mixed_production_once():
    user = User.objects.create_user(username="history-mixed-serving")
    farm = get_or_create_user_farm(user)
    grain = IngredientModel.objects.create(farm=farm, name="Pszenica historyczna")
    supplement = IngredientModel.objects.create(farm=farm, name="Premiks historyczny")
    recipe = RecipeModel.objects.create(farm=farm, name="Historyczny tucznik")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=grain, percentage=Decimal("80.00"))
    RecipeItemModel.objects.create(recipe=recipe, ingredient=supplement, percentage=Decimal("20.00"))
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 1, 5),
        time="12:30",
        quantity_kg=Decimal("2000.00"),
        status=ProductionModel.Statuses.QUEUED,
        feed_cost_total=Decimal("3000.00"),
        feed_cost_per_kg=Decimal("1.50000"),
    )
    ProductionModel.objects.filter(pk=production.pk).update(status=ProductionModel.Statuses.COMPLETED)
    production.refresh_from_db()
    product = FeedProductModel.objects.create(
        farm=farm,
        name=recipe.name,
        recipe=recipe,
        source_type=FeedProductModel.SourceTypes.PRODUCED,
    )
    batch = FinishedFeedBatchModel.objects.create(
        farm=farm,
        product=product,
        production=production,
        batch_date=production.date,
        initial_quantity_kg=production.quantity_kg,
        remaining_quantity_kg=production.quantity_kg,
        cost_per_kg=production.feed_cost_per_kg,
        total_cost=production.feed_cost_total,
    )

    migration = import_module("feed.migrations.0009_backfill_automatic_feed_servings")
    migration.backfill_automatic_feed_servings(django_apps, None)
    migration.backfill_automatic_feed_servings(django_apps, None)

    production.refresh_from_db()
    batch.refresh_from_db()
    serving = FeedServingModel.objects.get(automatic_for_production=production)
    assert serving.quantity_kg == Decimal("2000.00")
    assert serving.time.strftime("%H:%M") == "12:30"
    assert serving.total_cost == Decimal("3000.00")
    assert production.completion_feed_serving_mode == "AUTO_FULL_PRODUCTION"
    assert batch.remaining_quantity_kg == Decimal("0.00")
    assert FeedServingAllocationModel.objects.filter(serving=serving, batch=batch).count() == 1
    assert FeedServingModel.objects.filter(automatic_for_production=production).count() == 1
