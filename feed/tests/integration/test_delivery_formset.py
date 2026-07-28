from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from feed.actions.deliveries import create_deliveries, update_delivery
from feed.actions.inventory import InventoryActions
from feed.actions.productions import complete_production
from feed.forms import DeliveryForm, DeliveryFormSet
from feed.models import (
    DeliveryModel,
    IngredientModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)


def delivery_formset_data(rows):
    data = {
        "deliveries-TOTAL_FORMS": str(len(rows)),
        "deliveries-INITIAL_FORMS": "1" if rows else "0",
        "deliveries-MIN_NUM_FORMS": "0",
        "deliveries-MAX_NUM_FORMS": "1000",
    }
    for index, row in enumerate(rows):
        for field, value in row.items():
            data[f"deliveries-{index}-{field}"] = value
    return data


def valid_row(ingredient, *, quantity="100.00", price="1.20000", delivery_date=date(2026, 7, 1)):
    return {
        "date": delivery_date.isoformat(),
        "ingredient": str(ingredient.pk),
        "quantity_kg": quantity,
        "quantity_kg_unit": "kg",
        "price_per_kg": price,
        "price_per_kg_unit": "kg",
    }


@pytest.fixture
def delivery_client(client):
    user = get_user_model().objects.create_user(username="delivery-user", password="password")
    farm = get_or_create_user_farm(user)
    client.login(username="delivery-user", password="password")
    return client, user, farm


@pytest.mark.django_db
def test_add_delivery_get_uses_formset_template_and_initial_row(delivery_client):
    client, _user, farm = delivery_client
    own = IngredientModel.objects.create(farm=farm, name="Pszenica")
    other_user = get_user_model().objects.create_user(username="other-delivery-user")
    other_farm = get_or_create_user_farm(other_user)
    other = IngredientModel.objects.create(farm=other_farm, name="Cudza soja")

    response = client.get(reverse("add_delivery"))

    assert response.status_code == 200
    assert "feed/delivery_form.html" in [template.name for template in response.templates]
    assert response.context["formset"].total_form_count() == 1
    assert response.context["formset"].forms[0].initial["date"]
    assert list(response.context["formset"].forms[0].fields["ingredient"].queryset) == [own]
    assert other not in response.context["formset"].forms[0].fields["ingredient"].queryset
    assert b'id_deliveries-TOTAL_FORMS' in response.content
    assert b'delivery-row-template' in response.content
    assert response.content.count(b'price_per_kg_unit') >= 2
    assert b'Jednostka ceny' in response.content
    assert b'app.js?v=20260728-price-units' in response.content


@pytest.mark.django_db
def test_formset_rejects_foreign_ingredient_and_preserves_other_row(delivery_client):
    client, _user, farm = delivery_client
    own = IngredientModel.objects.create(farm=farm, name="Jęczmień")
    other_user = get_user_model().objects.create_user(username="foreign-delivery-user")
    other = IngredientModel.objects.create(
        farm=get_or_create_user_farm(other_user),
        name="Obca kukurydza",
    )
    data = delivery_formset_data([
        valid_row(own, quantity="321.00"),
        valid_row(other, quantity="50.00"),
    ])

    response = client.post(reverse("add_delivery"), data)

    assert response.status_code == 200
    assert DeliveryModel.objects.count() == 0
    formset = response.context["formset"]
    assert "ingredient" in formset.forms[1].errors
    assert formset.forms[0]["quantity_kg"].value() == "321.00"
    assert "Nie przyjęto żadnej dostawy" in response.content.decode()


@pytest.mark.django_db
def test_formset_ignores_blank_extra_row_and_requires_active_delivery(delivery_client):
    client, _user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Owies")

    saved = client.post(
        reverse("add_delivery"),
        delivery_formset_data([valid_row(ingredient), {}]),
    )

    assert saved.status_code == 302
    assert DeliveryModel.objects.filter(ingredient=ingredient).count() == 1

    empty = client.post(
        reverse("add_delivery"),
        delivery_formset_data([{"DELETE": "on"}]),
    )
    assert empty.status_code == 200
    assert "Dodaj przynajmniej jedną dostawę" in empty.content.decode()


@pytest.mark.django_db
def test_multiple_rows_create_distinct_fifo_deliveries_and_movements(delivery_client):
    client, _user, farm = delivery_client
    wheat = IngredientModel.objects.create(farm=farm, name="Pszenżyto")
    soy = IngredientModel.objects.create(farm=farm, name="Soja")
    rows = [
        valid_row(wheat, quantity="100.00", price="1.00000"),
        valid_row(soy, quantity="2.00", price="2.00000"),
        valid_row(wheat, quantity="0.5", price="1.50000", delivery_date=date(2026, 7, 2)),
    ]
    rows[1]["quantity_kg_unit"] = "t"
    rows[1]["price_per_kg"] = "1250"
    rows[1]["price_per_kg_unit"] = "t"
    rows[2]["price_per_kg"] = "987.50"
    rows[2]["price_per_kg_unit"] = "t"

    response = client.post(reverse("add_delivery"), delivery_formset_data(rows))

    assert response.status_code == 302
    deliveries = list(DeliveryModel.objects.order_by("id"))
    assert len(deliveries) == 3
    assert DeliveryModel.objects.filter(ingredient=wheat).count() == 2
    assert [delivery.remaining_quantity_kg for delivery in deliveries] == [
        Decimal("100.00"),
        Decimal("2000.00"),
        Decimal("0.50"),
    ]
    assert [delivery.price_per_kg for delivery in deliveries] == [
        Decimal("1.00000"),
        Decimal("1.25000"),
        Decimal("0.98750"),
    ]
    assert InventoryMovementModel.objects.filter(
        farm=farm,
        movement_type=InventoryMovementModel.Types.DELIVERY,
    ).count() == 3
    assert InventoryActions(farm).balances() == {
        wheat.pk: Decimal("100.50"),
        soy.pk: Decimal("2000.00"),
    }
    audits = AuditLogModel.objects.filter(
        farm=farm,
        action="CREATE",
        model_label="feed.DeliveryModel",
    )
    assert audits.count() == 3
    assert all("Dostawa:" in audit.object_repr for audit in audits)
    assert any("Pszenżyto" in audit.object_repr and "100 kg" in audit.object_repr for audit in audits)


@pytest.mark.django_db
def test_invalid_row_prevents_all_delivery_writes(delivery_client):
    client, _user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Żyto")
    invalid = valid_row(ingredient, quantity="0")

    response = client.post(
        reverse("add_delivery"),
        delivery_formset_data([valid_row(ingredient), invalid]),
    )

    assert response.status_code == 200
    assert DeliveryModel.objects.count() == 0
    assert InventoryMovementModel.objects.count() == 0


@pytest.mark.django_db
def test_blank_row_with_only_default_unit_selectors_is_ignored(delivery_client):
    client, _user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Puste selektory")
    blank = {
        "quantity_kg_unit": "kg",
        "price_per_kg_unit": "kg",
    }

    response = client.post(
        reverse("add_delivery"),
        delivery_formset_data([valid_row(ingredient), blank]),
    )

    assert response.status_code == 302
    assert DeliveryModel.objects.filter(ingredient=ingredient).count() == 1


@pytest.mark.django_db
def test_invalid_price_unit_and_non_positive_price_keep_bound_unit(delivery_client):
    client, _user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Cena walidowana")

    unknown = client.post(
        reverse("add_delivery"),
        delivery_formset_data([
            valid_row(ingredient) | {"price_per_kg_unit": "l"},
        ]),
    )
    zero = client.post(
        reverse("add_delivery"),
        delivery_formset_data([
            valid_row(ingredient) | {
                "price_per_kg": "0",
                "price_per_kg_unit": "t",
            },
        ]),
    )

    assert unknown.status_code == zero.status_code == 200
    assert "price_per_kg_unit" in unknown.context["formset"].forms[0].errors
    assert "price_per_kg" in zero.context["formset"].forms[0].errors
    assert zero.context["formset"].forms[0]["price_per_kg_unit"].value() == "t"
    assert not DeliveryModel.objects.exists()


@pytest.mark.django_db
def test_edit_delivery_accepts_price_per_tonne_without_rebuild(delivery_client):
    _client, user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Edycja ceny")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 1),
        quantity_kg=Decimal("2000.00"),
        remaining_quantity_kg=Decimal("2000.00"),
        price_per_kg=Decimal("1.00000"),
    )
    InventoryActions(farm).sync_delivery(delivery)
    form = DeliveryForm(
        {
            "date": "2026-07-01",
            "ingredient": ingredient.pk,
            "quantity_kg": "2",
            "quantity_kg_unit": "t",
            "price_per_kg": "1250",
            "price_per_kg_unit": "t",
        },
        instance=delivery,
        farm=farm,
    )
    assert form.is_valid(), form.errors

    with patch.object(InventoryActions, "rebuild") as rebuild:
        updated = update_delivery(form, farm=farm, user=user)

    updated.refresh_from_db()
    assert updated.price_per_kg == Decimal("1.25000")
    assert updated.quantity_kg == Decimal("2000.00")
    rebuild.assert_not_called()


@pytest.mark.django_db
def test_quantity_change_still_rebuilds_inventory(delivery_client):
    _client, user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Edycja ilości")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 1),
        quantity_kg=Decimal("100.00"),
        remaining_quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("1.00000"),
    )
    form = DeliveryForm(
        {
            "date": "2026-07-01",
            "ingredient": ingredient.pk,
            "quantity_kg": "150",
            "quantity_kg_unit": "kg",
            "price_per_kg": "1",
            "price_per_kg_unit": "kg",
        },
        instance=delivery,
        farm=farm,
    )
    assert form.is_valid(), form.errors

    with patch.object(InventoryActions, "rebuild") as rebuild:
        update_delivery(form, farm=farm, user=user)

    rebuild.assert_called_once_with()


@pytest.mark.django_db
def test_date_change_still_rebuilds_fifo_order(delivery_client):
    _client, user, farm = delivery_client
    ingredient = IngredientModel.objects.create(farm=farm, name="Edycja daty")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 2),
        quantity_kg=Decimal("100.00"),
        remaining_quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("1.00000"),
    )
    form = DeliveryForm(
        {
            "date": "2026-07-01",
            "ingredient": ingredient.pk,
            "quantity_kg": "100",
            "quantity_kg_unit": "kg",
            "price_per_kg": "1",
            "price_per_kg_unit": "kg",
        },
        instance=delivery,
        farm=farm,
    )
    assert form.is_valid(), form.errors

    with patch.object(InventoryActions, "rebuild") as rebuild:
        update_delivery(form, farm=farm, user=user)

    rebuild.assert_called_once_with()


@pytest.mark.django_db
def test_price_edit_preserves_historical_fifo_and_production_cost_snapshot(
    delivery_client,
):
    _client, user, farm = delivery_client
    ingredient = IngredientModel.objects.create(
        farm=farm,
        name="Historyczna cena",
    )
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 1),
        quantity_kg=Decimal("1000.00"),
        remaining_quantity_kg=Decimal("1000.00"),
        price_per_kg=Decimal("1.00000"),
    )
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="Koszt historyczny")
    RecipeItemModel.objects.create(
        recipe=recipe,
        ingredient=ingredient,
        percentage=Decimal("100.00"),
    )
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 7, 2),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    complete_production(farm, production.pk, user=user)
    usage = ProductionIngredientUsageModel.objects.get(
        production=production,
        delivery=delivery,
    )
    production.refresh_from_db()
    historical_total = production.feed_cost_total
    historical_usage_price = usage.unit_price

    form = DeliveryForm(
        {
            "date": "2026-07-01",
            "ingredient": ingredient.pk,
            "quantity_kg": "1",
            "quantity_kg_unit": "t",
            "price_per_kg": "2000",
            "price_per_kg_unit": "t",
        },
        instance=DeliveryModel.objects.get(pk=delivery.pk),
        farm=farm,
    )
    assert form.is_valid(), form.errors
    update_delivery(form, farm=farm, user=user)

    production.refresh_from_db()
    usage.refresh_from_db()
    movement = InventoryMovementModel.objects.get(
        farm=farm,
        movement_type=InventoryMovementModel.Types.DELIVERY,
        source_id=str(delivery.pk),
    )
    assert production.feed_cost_total == historical_total
    assert usage.unit_price == historical_usage_price
    assert movement.unit_price == Decimal("2.00000")


@pytest.mark.django_db(transaction=True)
def test_price_only_update_invalidates_cache_once_and_rolls_back_on_sync_error():
    user = get_user_model().objects.create_user(username="price-update-user")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Rollback ceny")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 7, 1),
        quantity_kg=Decimal("100.00"),
        remaining_quantity_kg=Decimal("100.00"),
        price_per_kg=Decimal("1.00000"),
    )

    def price_form(value):
        form = DeliveryForm(
            {
                "date": "2026-07-01",
                "ingredient": ingredient.pk,
                "quantity_kg": "100",
                "quantity_kg_unit": "kg",
                "price_per_kg": value,
                "price_per_kg_unit": "kg",
            },
            instance=DeliveryModel.objects.get(pk=delivery.pk),
            farm=farm,
        )
        assert form.is_valid(), form.errors
        return form

    with patch("common.cache.invalidate_farm_cache") as invalidate_cache:
        update_delivery(price_form("1.25"), farm=farm, user=user)
    invalidate_cache.assert_called_once()

    with patch.object(
        InventoryActions,
        "sync_delivery",
        side_effect=RuntimeError("sync error"),
    ), pytest.raises(RuntimeError, match="sync error"):
        update_delivery(price_form("1.50"), farm=farm, user=user)

    delivery.refresh_from_db()
    assert delivery.price_per_kg == Decimal("1.25000")


@pytest.mark.django_db
def test_price_only_update_query_count_does_not_grow_with_other_deliveries():
    def measured_update(suffix, background_count):
        owner = get_user_model().objects.create_user(
            username=f"price-query-{suffix}"
        )
        farm = get_or_create_user_farm(
            owner
        )
        ingredient = IngredientModel.objects.create(farm=farm, name=f"Składnik {suffix}")
        DeliveryModel.objects.bulk_create([
            DeliveryModel(
                ingredient=ingredient,
                date=date(2026, 6, 1),
                quantity_kg=Decimal("100.00"),
                remaining_quantity_kg=Decimal("100.00"),
                price_per_kg=Decimal("1.00000"),
            )
            for _ in range(background_count)
        ])
        delivery = DeliveryModel.objects.create(
            ingredient=ingredient,
            date=date(2026, 7, 1),
            quantity_kg=Decimal("100.00"),
            remaining_quantity_kg=Decimal("100.00"),
            price_per_kg=Decimal("1.00000"),
        )
        InventoryActions(farm).sync_delivery(delivery)
        form = DeliveryForm(
            {
                "date": "2026-07-01",
                "ingredient": ingredient.pk,
                "quantity_kg": "100",
                "quantity_kg_unit": "kg",
                "price_per_kg": "1.25",
                "price_per_kg_unit": "kg",
            },
            instance=delivery,
            farm=farm,
        )
        assert form.is_valid(), form.errors
        with CaptureQueriesContext(connection) as queries:
            update_delivery(form, farm=farm, user=owner)
        return len(queries)

    assert measured_update("small", 0) == measured_update("large", 50)


@pytest.mark.django_db(transaction=True)
def test_create_deliveries_rolls_back_movements_and_cache_when_later_sync_fails():
    user = get_user_model().objects.create_user(username="atomic-delivery-user")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Groch")
    rows = [valid_row(ingredient), valid_row(ingredient, quantity="200.00")]
    formset = DeliveryFormSet(
        delivery_formset_data(rows),
        prefix="deliveries",
        initial=[{"date": date(2026, 7, 1)}],
        form_kwargs={"farm": farm},
    )
    assert formset.is_valid() is True

    original_sync = InventoryActions.sync_delivery
    call_count = 0

    def fail_second_sync(inventory, delivery, *, user=None):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("symulowany błąd synchronizacji")
        return original_sync(inventory, delivery, user=user)

    with patch.object(InventoryActions, "sync_delivery", fail_second_sync), \
            patch("common.cache.invalidate_farm_cache") as invalidate_cache:
        with pytest.raises(RuntimeError, match="symulowany błąd"):
            create_deliveries(formset, farm=farm, user=user)

    assert DeliveryModel.objects.count() == 0
    assert InventoryMovementModel.objects.count() == 0
    assert AuditLogModel.objects.filter(farm=farm, action="CREATE").count() == 0
    invalidate_cache.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_create_deliveries_invalidates_inventory_cache_once_after_commit():
    user = get_user_model().objects.create_user(username="cache-delivery-user")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Bobik")
    rows = [valid_row(ingredient), valid_row(ingredient, quantity="200.00")]
    formset = DeliveryFormSet(
        delivery_formset_data(rows),
        prefix="deliveries",
        initial=[{"date": date(2026, 7, 1)}],
        form_kwargs={"farm": farm},
    )
    assert formset.is_valid() is True

    with patch("common.cache.invalidate_farm_cache") as invalidate_cache:
        created = create_deliveries(formset, farm=farm, user=user)

    assert len(created) == 2
    invalidate_cache.assert_called_once()
