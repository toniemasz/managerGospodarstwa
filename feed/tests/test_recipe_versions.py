from datetime import date
from decimal import Decimal
import importlib

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from feed.forms import ProductionForm
from feed.models import (
    DeliveryModel,
    IngredientModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
    RecipeVersionItemModel,
    RecipeVersionModel,
)
from feed.services.feed_management_service import FeedManagementService
from feed.use_cases.edit_recipe_create_version import RecipeVersionService


@pytest.fixture
def versioned_feed():
    user = get_user_model().objects.create_user(username="recipe-version", password="password")
    farm = get_or_create_user_farm(user)
    barley = IngredientModel.objects.create(farm=farm, name="Jęczmień")
    soy = IngredientModel.objects.create(farm=farm, name="Soja")
    DeliveryModel.objects.create(
        ingredient=barley,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.00000"),
    )
    DeliveryModel.objects.create(
        ingredient=soy,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("2.00000"),
    )
    recipe = RecipeModel.objects.create(farm=farm, name="Grower")
    barley_item = RecipeItemModel.objects.create(
        recipe=recipe,
        ingredient=barley,
        percentage=Decimal("100.00"),
    )
    version, created = RecipeVersionService(farm=farm, user=user).ensure_current_version(
        recipe,
        change_note="Start",
    )
    assert created is True
    return {
        "user": user,
        "farm": farm,
        "barley": barley,
        "soy": soy,
        "recipe": recipe,
        "barley_item": barley_item,
        "version": version,
    }


def _create_second_version(data, *, barley_percentage="50.00", soy_percentage="50.00"):
    version = RecipeVersionService(
        farm=data["farm"],
        user=data["user"],
    ).create_new_version(
        recipe=data["recipe"],
        source_version=data["version"],
        items=[
            {"ingredient": data["barley"], "percentage": Decimal(barley_percentage)},
            {"ingredient": data["soy"], "percentage": Decimal(soy_percentage)},
        ],
        change_note="Korekta składu",
    )
    return version


def _complete_production(farm, recipe, version, quantity, production_date, user, custom_recipe_data=None):
    production = ProductionModel.objects.create(
        recipe=recipe,
        recipe_version=version,
        date=production_date,
        quantity_kg=Decimal(quantity),
        custom_recipe_data=custom_recipe_data,
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    success, message = FeedManagementService(farm).complete_production(production.pk, user=user)
    assert success is True, message
    production.refresh_from_db()
    return production


def _version_formset_data(items):
    data = {
        "items-TOTAL_FORMS": str(len(items)),
        "items-INITIAL_FORMS": "0",
        "items-MIN_NUM_FORMS": "0",
        "items-MAX_NUM_FORMS": "1000",
    }
    for index, item in enumerate(items):
        if item.get("id"):
            data[f"items-{index}-id"] = item["id"]
        data[f"items-{index}-ingredient"] = item["ingredient"].id
        data[f"items-{index}-percentage"] = item["percentage"]
    return data


def _existing_version_formset_data(version, items):
    data = _version_formset_data(items)
    data["items-INITIAL_FORMS"] = str(version.items.count())
    return data


@pytest.mark.django_db
def test_recipe_edit_creates_version_only_when_composition_changes(versioned_feed):
    recipe = versioned_feed["recipe"]
    version_1 = versioned_feed["version"]
    production = _complete_production(
        versioned_feed["farm"],
        recipe,
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )

    version_2 = _create_second_version(versioned_feed)
    version_1.refresh_from_db()
    production.refresh_from_db()

    assert version_2.version_number == 2
    assert version_2.is_current is True
    assert version_1.is_current is False
    assert version_1.valid_to is not None
    assert production.recipe_version_id == version_1.id
    assert ProductionIngredientUsageModel.objects.filter(production=production).count() == 1

    recipe.name = "Grower renamed"
    recipe.save(update_fields=["name"])
    _, created = RecipeVersionService(
        farm=versioned_feed["farm"],
        user=versioned_feed["user"],
    ).ensure_current_version(recipe, change_note="Zmiana nazwy")

    assert created is False
    assert RecipeVersionModel.objects.filter(recipe=recipe).count() == 2
    audit = AuditLogModel.objects.filter(action="RECIPE_VERSION_CREATED").latest("id")
    assert audit.metadata["recipe_id"] == str(recipe.id)
    assert audit.metadata["recipe_version_id"] == str(version_2.id)


@pytest.mark.django_db
def test_new_production_gets_current_recipe_version_from_form(versioned_feed):
    version_2 = _create_second_version(versioned_feed)
    form = ProductionForm(
        data={
            "date": date(2026, 2, 3),
            "time": "08:00",
            "recipe": versioned_feed["recipe"].id,
            "quantity_kg": "100.00",
        },
        farm=versioned_feed["farm"],
    )

    assert form.is_valid() is True
    production = form.save()

    assert production.recipe_version_id == version_2.id


@pytest.mark.django_db
def test_completed_production_uses_assigned_version_not_current_recipe_items(versioned_feed):
    recipe = versioned_feed["recipe"]
    version_1 = versioned_feed["version"]
    production = ProductionModel.objects.create(
        recipe=recipe,
        recipe_version=version_1,
        date=date(2026, 2, 5),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    _create_second_version(versioned_feed)

    success, message = FeedManagementService(versioned_feed["farm"]).complete_production(
        production.pk,
        user=versioned_feed["user"],
    )

    assert success is True, message
    usages = list(ProductionIngredientUsageModel.objects.filter(production=production))
    assert len(usages) == 1
    assert usages[0].ingredient_id == versioned_feed["barley"].id
    assert usages[0].quantity_kg == Decimal("100.00")


@pytest.mark.django_db
def test_production_requirements_fallback_to_current_recipe_items_when_version_is_null(versioned_feed):
    _create_second_version(versioned_feed)
    production = ProductionModel.objects.create(
        recipe=versioned_feed["recipe"],
        recipe_version=None,
        date=date(2026, 2, 7),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )

    success, message = FeedManagementService(versioned_feed["farm"]).complete_production(
        production.pk,
        user=versioned_feed["user"],
    )

    assert success is True, message
    usages = {
        usage.ingredient_id: usage.quantity_kg
        for usage in ProductionIngredientUsageModel.objects.filter(production=production)
    }
    assert usages == {
        versioned_feed["barley"].id: Decimal("50.00"),
        versioned_feed["soy"].id: Decimal("50.00"),
    }


@pytest.mark.django_db
def test_editing_existing_version_recalculates_only_productions_assigned_to_that_version(versioned_feed):
    recipe = versioned_feed["recipe"]
    version_1 = versioned_feed["version"]
    production_v1 = _complete_production(
        versioned_feed["farm"],
        recipe,
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )
    version_2 = _create_second_version(versioned_feed)
    production_v2 = _complete_production(
        versioned_feed["farm"],
        recipe,
        version_2,
        "100.00",
        date(2026, 2, 2),
        versioned_feed["user"],
    )

    result = RecipeVersionService(
        farm=versioned_feed["farm"],
        user=versioned_feed["user"],
    ).update_existing_version(
        version=version_2,
        confirm_recalculate=True,
        items=[
            {"ingredient": versioned_feed["barley"], "percentage": Decimal("20.00")},
            {"ingredient": versioned_feed["soy"], "percentage": Decimal("80.00")},
        ],
    )

    production_v1.refresh_from_db()
    production_v2.refresh_from_db()
    assert result.completed_count == 1
    assert production_v1.recipe_version_id == version_1.id
    assert production_v2.recipe_version_id == version_2.id
    assert production_v1.feed_cost_total == Decimal("100.00")
    assert production_v2.feed_cost_total == Decimal("180.00")
    assert {
        usage.ingredient_id: usage.quantity_kg
        for usage in ProductionIngredientUsageModel.objects.filter(production=production_v1)
    } == {versioned_feed["barley"].id: Decimal("100.00")}
    assert {
        usage.ingredient_id: usage.quantity_kg
        for usage in ProductionIngredientUsageModel.objects.filter(production=production_v2)
    } == {
        versioned_feed["barley"].id: Decimal("20.00"),
        versioned_feed["soy"].id: Decimal("80.00"),
    }
    assert AuditLogModel.objects.filter(action="RECIPE_VERSION_UPDATED").exists()
    audit = AuditLogModel.objects.filter(action="RECIPE_VERSION_PRODUCTIONS_RECALCULATED").latest("id")
    assert audit.metadata["production_ids"] == [str(production_v2.id)]


@pytest.mark.django_db
def test_editing_version_with_productions_requires_confirmation(versioned_feed):
    version_1 = versioned_feed["version"]
    _complete_production(
        versioned_feed["farm"],
        versioned_feed["recipe"],
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )

    with pytest.raises(ValidationError):
        RecipeVersionService(farm=versioned_feed["farm"], user=versioned_feed["user"]).update_existing_version(
            version=version_1,
            confirm_recalculate=False,
            items=[{"ingredient": versioned_feed["barley"], "percentage": Decimal("100.00")}],
        )

    item = RecipeVersionItemModel.objects.get(recipe_version=version_1)
    assert item.percentage == Decimal("100.00")
    assert not AuditLogModel.objects.filter(action="RECIPE_VERSION_UPDATED").exists()


@pytest.mark.django_db
def test_adding_new_version_does_not_recalculate_existing_productions(versioned_feed):
    version_1 = versioned_feed["version"]
    production = _complete_production(
        versioned_feed["farm"],
        versioned_feed["recipe"],
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )

    version_2 = _create_second_version(versioned_feed, barley_percentage="10.00", soy_percentage="90.00")

    production.refresh_from_db()
    assert version_2.is_current is True
    assert production.recipe_version_id == version_1.id
    assert production.feed_cost_total == Decimal("100.00")
    assert RecipeItemModel.objects.get(recipe=versioned_feed["recipe"], ingredient=versioned_feed["soy"]).percentage == Decimal("90.00")


@pytest.mark.django_db
def test_editing_version_preserves_custom_recipe_data_as_override(versioned_feed):
    version_1 = versioned_feed["version"]
    _create_second_version(versioned_feed)
    production = _complete_production(
        versioned_feed["farm"],
        versioned_feed["recipe"],
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
        custom_recipe_data={str(versioned_feed["barley"].id): "100.00"},
    )

    result = RecipeVersionService(farm=versioned_feed["farm"], user=versioned_feed["user"]).update_existing_version(
        version=version_1,
        confirm_recalculate=True,
        items=[{"ingredient": versioned_feed["barley"], "percentage": Decimal("100.00")}],
    )

    production.refresh_from_db()
    usage = ProductionIngredientUsageModel.objects.get(production=production)
    assert result.custom_recipe_count == 1
    assert production.custom_recipe_data == {str(versioned_feed["barley"].id): "100.00"}
    assert usage.ingredient_id == versioned_feed["barley"].id
    assert usage.quantity_kg == Decimal("100.00")


@pytest.mark.django_db
def test_recipe_detail_shows_version_actions_without_manual_recalculation_panel(client, versioned_feed):
    client.login(username="recipe-version", password="password")
    _complete_production(
        versioned_feed["farm"],
        versioned_feed["recipe"],
        versioned_feed["version"],
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )

    response = client.get(reverse("recipe_detail", args=[versioned_feed["recipe"].id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Historia zmian receptury" in content
    assert "Przelicz historyczne śrutowania" not in content
    assert "Podgląd" in content
    assert "Edytuj wersję" in content
    assert "Utwórz nową wersję" in content
    assert response.context["recipe_versions"][0].production_count == 1


@pytest.mark.django_db
def test_recipe_version_edit_view_requires_confirmation_and_then_recalculates(client, versioned_feed):
    client.login(username="recipe-version", password="password")
    version_1 = versioned_feed["version"]
    production = _complete_production(
        versioned_feed["farm"],
        versioned_feed["recipe"],
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )
    item = RecipeVersionItemModel.objects.get(recipe_version=version_1)
    data = _existing_version_formset_data(version_1, [
        {"id": item.id, "ingredient": versioned_feed["barley"], "percentage": "50.00"},
        {"ingredient": versioned_feed["soy"], "percentage": "50.00"},
    ])

    response = client.post(reverse("edit_recipe_version", args=[versioned_feed["recipe"].id, version_1.id]), data)

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.percentage == Decimal("100.00")
    assert "Potwierdź" in response.content.decode()

    data["confirm_recalculate"] = "on"
    response = client.post(reverse("edit_recipe_version", args=[versioned_feed["recipe"].id, version_1.id]), data)

    assert response.status_code == 302
    production.refresh_from_db()
    assert production.feed_cost_total == Decimal("150.00")
    assert {
        usage.ingredient_id: usage.quantity_kg
        for usage in ProductionIngredientUsageModel.objects.filter(production=production)
    } == {
        versioned_feed["barley"].id: Decimal("50.00"),
        versioned_feed["soy"].id: Decimal("50.00"),
    }


@pytest.mark.django_db
def test_add_recipe_version_view_creates_future_version_without_touching_old_production(client, versioned_feed):
    client.login(username="recipe-version", password="password")
    version_1 = versioned_feed["version"]
    production = _complete_production(
        versioned_feed["farm"],
        versioned_feed["recipe"],
        version_1,
        "100.00",
        date(2026, 2, 1),
        versioned_feed["user"],
    )
    data = _version_formset_data([
        {"ingredient": versioned_feed["barley"], "percentage": "25.00"},
        {"ingredient": versioned_feed["soy"], "percentage": "75.00"},
    ])

    response = client.post(reverse("add_recipe_version", args=[versioned_feed["recipe"].id, version_1.id]), data)

    assert response.status_code == 302
    version_2 = RecipeVersionModel.objects.get(recipe=versioned_feed["recipe"], version_number=2)
    production.refresh_from_db()
    assert version_2.is_current is True
    assert production.recipe_version_id == version_1.id
    assert production.feed_cost_total == Decimal("100.00")


@pytest.mark.django_db
def test_recipe_version_detail_view_shows_only_current_farm_version(client, versioned_feed):
    client.login(username="recipe-version", password="password")

    response = client.get(reverse("recipe_version_detail", args=[versioned_feed["recipe"].id, versioned_feed["version"].id]))

    assert response.status_code == 200
    assert "Grower v1" in response.content.decode()

    other_user = get_user_model().objects.create_user(username="other-version", password="password")
    other_farm = get_or_create_user_farm(other_user)
    other_ingredient = IngredientModel.objects.create(farm=other_farm, name="Cudza pszenica")
    other_recipe = RecipeModel.objects.create(farm=other_farm, name="Cudza")
    RecipeItemModel.objects.create(recipe=other_recipe, ingredient=other_ingredient, percentage=Decimal("100.00"))
    other_version, _ = RecipeVersionService(farm=other_farm, user=other_user).ensure_current_version(other_recipe)

    response = client.get(reverse("recipe_version_detail", args=[other_recipe.id, other_version.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_recipe_version_backfill_migration_preserves_existing_costs_and_fifo_state():
    user = get_user_model().objects.create_user(username="migration-recipe-version")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Migracyjny jęczmień")
    recipe = RecipeModel.objects.create(farm=farm, name="Migracyjna")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal("100.00"))
    production = ProductionModel(
        recipe=recipe,
        recipe_version=None,
        date=date(2026, 3, 1),
        quantity_kg=Decimal("250.00"),
        status=ProductionModel.Statuses.COMPLETED,
        feed_cost_total=Decimal("123.45"),
        feed_cost_per_kg=Decimal("0.49380"),
    )
    production._skip_inventory_sync = True
    production.save()

    migration = importlib.import_module("feed.migrations.0006_recipe_versions")
    migration.backfill_recipe_versions(django_apps, None)

    version = RecipeVersionModel.objects.get(recipe=recipe, version_number=1)
    production.refresh_from_db()
    assert version.is_current is True
    assert RecipeVersionItemModel.objects.get(recipe_version=version).percentage == Decimal("100.00")
    assert production.recipe_version_id == version.id
    assert production.feed_cost_total == Decimal("123.45")
    assert production.feed_cost_per_kg == Decimal("0.49380")
    assert not ProductionIngredientUsageModel.objects.filter(production=production).exists()
    assert not InventoryMovementModel.objects.filter(
        farm=farm,
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_id=str(production.id),
    ).exists()
