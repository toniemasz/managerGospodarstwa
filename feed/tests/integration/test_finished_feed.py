from datetime import date
from decimal import Decimal

import pytest
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from farms.services.farm_service import get_or_create_user_farm
from feed.actions.finished_feed import (
    create_feed_serving,
    create_purchased_ready_feed_product,
    create_ready_feed_delivery,
    delete_feed_serving,
)
from feed.models import (
    FeedProductModel,
    FeedServingAllocationModel,
    FinishedFeedBatchModel,
    ReadyFeedDeliveryModel,
)
from costs.models import CostModel
from feed.selectors.production_costs import ProductionCostSelector


@pytest.fixture
def ready_feed():
    user = User.objects.create_user(username="ready-feed")
    farm = get_or_create_user_farm(user)
    product = FeedProductModel.objects.create(
        farm=farm, name="Bebito", source_type=FeedProductModel.SourceTypes.PURCHASED_READY,
    )
    return user, farm, product


@pytest.mark.django_db
def test_purchased_ready_feed_creates_batch_without_production(ready_feed):
    user, farm, product = ready_feed
    delivery = create_ready_feed_delivery(
        farm=farm, product=product, date=date(2026, 7, 1),
        quantity_kg=Decimal("500"), price_per_kg=Decimal("1.25"), user=user,
    )
    batch = FinishedFeedBatchModel.objects.get(ready_feed_delivery=delivery)
    assert batch.production_id is None
    assert batch.remaining_quantity_kg == Decimal("500")
    assert batch.total_cost == Decimal("625.00")
    assert not CostModel.objects.filter(farm=farm).exists()
    assert ProductionCostSelector(farm).calculate()["total_cost"] == Decimal("0.00")


@pytest.mark.django_db
def test_manual_serving_uses_finished_batches_fifo_and_delete_restores_them(ready_feed):
    user, farm, product = ready_feed
    first = create_ready_feed_delivery(farm=farm, product=product, date=date(2026, 7, 1), quantity_kg=Decimal("100"), price_per_kg=Decimal("1"), user=user).batch
    second = create_ready_feed_delivery(farm=farm, product=product, date=date(2026, 7, 2), quantity_kg=Decimal("100"), price_per_kg=Decimal("2"), user=user).batch
    serving = create_feed_serving(farm=farm, product=product, date=date(2026, 7, 3), quantity_kg=Decimal("150"), user=user)
    allocations = list(FeedServingAllocationModel.objects.filter(serving=serving).order_by("batch__batch_date"))
    assert [item.quantity_kg for item in allocations] == [Decimal("100"), Decimal("50")]
    assert serving.total_cost == Decimal("200.00")
    first.refresh_from_db(); second.refresh_from_db()
    assert (first.remaining_quantity_kg, second.remaining_quantity_kg) == (Decimal("0"), Decimal("50"))
    delete_feed_serving(farm=farm, serving=serving)
    first.refresh_from_db(); second.refresh_from_db()
    assert (first.remaining_quantity_kg, second.remaining_quantity_kg) == (Decimal("100"), Decimal("100"))
    assert not CostModel.objects.filter(farm=farm).exists()
    assert ProductionCostSelector(farm).calculate()["total_cost"] == Decimal("0.00")


@pytest.mark.django_db
def test_manual_serving_cannot_exceed_finished_feed_stock(ready_feed):
    user, farm, product = ready_feed
    create_ready_feed_delivery(farm=farm, product=product, date=date(2026, 7, 1), quantity_kg=Decimal("100"), price_per_kg=Decimal("1"), user=user)
    with pytest.raises(ValidationError):
        create_feed_serving(farm=farm, product=product, date=date(2026, 7, 2), quantity_kg=Decimal("101"), user=user)
    assert not FeedServingAllocationModel.objects.exists()


@pytest.mark.django_db
def test_purchased_product_can_be_created_without_delivery(ready_feed):
    user, farm, _ = ready_feed
    client = Client()
    client.force_login(user)
    response = client.post(reverse("create_ready_feed_product"), {"name": " Starter "})
    assert response.status_code == 302
    product = FeedProductModel.objects.get(farm=farm, name="Starter")
    assert product.source_type == FeedProductModel.SourceTypes.PURCHASED_READY
    assert product.recipe_id is None
    assert product.is_active is True
    assert not ReadyFeedDeliveryModel.objects.filter(product=product).exists()
    assert not FinishedFeedBatchModel.objects.filter(product=product).exists()


@pytest.mark.django_db
def test_duplicate_product_names_are_rejected_case_insensitively(ready_feed):
    user, farm, _ = ready_feed
    client = Client(); client.force_login(user)
    first = client.post(reverse("create_ready_feed_product"), {"name": "Starter"})
    duplicate = client.post(reverse("create_ready_feed_product"), {"name": "starter"})
    assert first.status_code == 302
    assert duplicate.status_code == 200
    assert "już istnieje" in duplicate.content.decode()
    assert FeedProductModel.objects.filter(farm=farm, name__iexact="starter").count() == 1


@pytest.mark.django_db
def test_product_name_uniqueness_is_scoped_to_explicit_farm(ready_feed):
    _user, farm, _ = ready_feed
    other_user = User.objects.create_user(username="other-product-farm")
    other_farm = get_or_create_user_farm(other_user)

    own_product = create_purchased_ready_feed_product(farm=farm, name="Starter")
    other_product = create_purchased_ready_feed_product(farm=other_farm, name="Starter")

    assert own_product.farm_id == farm.pk
    assert other_product.farm_id == other_farm.pk


@pytest.mark.django_db(transaction=True)
def test_product_creation_converts_integrity_race_to_validation_error(ready_feed):
    _user, farm, _ = ready_feed
    with patch(
        "feed.actions.finished_feed.FeedProductModel.objects.create",
        side_effect=IntegrityError("concurrent duplicate"),
    ):
        with pytest.raises(ValidationError, match="już istnieje"):
            create_purchased_ready_feed_product(farm=farm, name="Wyścig")


@pytest.mark.django_db
def test_produced_product_name_cannot_be_reused_for_purchased_product(ready_feed):
    user, farm, _ = ready_feed
    FeedProductModel.objects.create(
        farm=farm,
        name="Grower",
        source_type=FeedProductModel.SourceTypes.PRODUCED,
    )
    client = Client(); client.force_login(user)
    response = client.post(reverse("create_ready_feed_product"), {"name": "grower"})
    assert response.status_code == 200
    assert FeedProductModel.objects.filter(farm=farm, name__iexact="grower").count() == 1


@pytest.mark.django_db
def test_delivery_ui_creates_separate_fifo_batches_and_manual_serving(ready_feed):
    user, farm, product = ready_feed
    client = Client(); client.force_login(user)
    first = client.post(reverse("add_ready_feed_delivery", args=[product.pk]), {
        "date": "2026-07-01",
        "quantity_kg": "200.00",
        "price_per_kg": "1.50000",
    })
    second = client.post(reverse("add_ready_feed_delivery", args=[product.pk]), {
        "date": "2026-07-02",
        "quantity_kg": "300.00",
        "price_per_kg": "1.75000",
    })
    assert first.status_code == second.status_code == 302
    assert ReadyFeedDeliveryModel.objects.filter(product=product).count() == 2
    assert FinishedFeedBatchModel.objects.filter(product=product).count() == 2
    assert sum(product.batches.values_list("remaining_quantity_kg", flat=True), Decimal("0.00")) == Decimal("500.00")
    first_delivery = product.deliveries.order_by("date").first()
    assert first_delivery.total_cost == Decimal("300.00")
    assert first_delivery.batch.cost_per_kg == Decimal("1.50000")
    assert first_delivery.batch.total_cost == Decimal("300.00")

    serving = client.post(reverse("create_feed_serving"), {
        "product": product.pk,
        "date": "2026-07-03",
        "time": "08:00",
        "quantity_kg": "250.00",
        "note": "Sektor A",
    })
    assert serving.status_code == 302
    allocations = list(product.servings.get().allocations.order_by("batch__batch_date"))
    assert [row.quantity_kg for row in allocations] == [Decimal("200.00"), Decimal("50.00")]


@pytest.mark.django_db
def test_finished_feed_ui_is_isolated_by_farm(ready_feed):
    user, _, product = ready_feed
    other = User.objects.create_user(username="other-ready")
    other_farm = get_or_create_user_farm(other)
    other_product = FeedProductModel.objects.create(farm=other_farm, name="Cudza", source_type=FeedProductModel.SourceTypes.PURCHASED_READY)
    client = Client(); client.force_login(user)
    response = client.post(reverse("create_feed_serving"), {
        "product": other_product.pk, "date": "2026-07-02", "quantity_kg": "1.00",
    })
    assert response.status_code == 200
    assert not other_product.servings.exists()

    delivery_response = client.post(reverse("add_ready_feed_delivery", args=[other_product.pk]), {
        "date": "2026-07-02", "quantity_kg": "10.00", "price_per_kg": "1.00",
    })
    assert delivery_response.status_code == 404
    assert not other_product.deliveries.exists()


@pytest.mark.django_db
def test_delivery_to_produced_product_is_not_publicly_available(ready_feed):
    user, farm, _ = ready_feed
    produced = FeedProductModel.objects.create(
        farm=farm, name="Wytworzona", source_type=FeedProductModel.SourceTypes.PRODUCED,
    )
    client = Client(); client.force_login(user)
    response = client.post(reverse("add_ready_feed_delivery", args=[produced.pk]), {
        "date": "2026-07-02", "quantity_kg": "10.00", "price_per_kg": "1.00",
    })
    assert response.status_code == 404
    assert not ReadyFeedDeliveryModel.objects.filter(product=produced).exists()


@pytest.mark.django_db
def test_finished_feed_list_exposes_delivery_action_only_for_purchased_product(ready_feed):
    user, farm, purchased = ready_feed
    produced = FeedProductModel.objects.create(
        farm=farm, name="Wytworzona", source_type=FeedProductModel.SourceTypes.PRODUCED,
    )
    client = Client(); client.force_login(user)
    response = client.get(reverse("finished_feed_inventory"))
    body = response.content.decode()
    assert reverse("create_ready_feed_product") in body
    assert reverse("add_ready_feed_delivery", args=[purchased.pk]) in body
    assert reverse("add_ready_feed_delivery", args=[produced.pk]) not in body
    assert "Dodaj gotową paszę" in body
    assert "Podawana automatycznie" in body
    assert "Kup gotową paszę" not in body


@pytest.mark.django_db
def test_delivery_form_does_not_accept_product_override(ready_feed):
    user, farm, product = ready_feed
    other = FeedProductModel.objects.create(
        farm=farm, name="Inna", source_type=FeedProductModel.SourceTypes.PURCHASED_READY,
    )
    client = Client(); client.force_login(user)
    response = client.post(reverse("add_ready_feed_delivery", args=[product.pk]), {
        "product": other.pk,
        "date": "2026-07-02",
        "quantity_kg": "10.00",
        "price_per_kg": "1.00",
    })
    assert response.status_code == 302
    assert product.deliveries.count() == 1
    assert other.deliveries.count() == 0
