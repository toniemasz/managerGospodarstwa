from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from farms.services.farm_service import get_or_create_user_farm
from feed.actions.finished_feed import create_feed_serving, create_ready_feed_delivery, delete_feed_serving
from feed.models import FeedProductModel, FeedServingAllocationModel, FinishedFeedBatchModel
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
def test_finished_feed_purchase_and_manual_serving_are_available_in_ui(ready_feed):
    user, farm, _ = ready_feed
    client = Client()
    client.force_login(user)
    purchase = client.post(reverse("purchase_ready_feed"), {
        "product_name": "Starter",
        "date": "2026-07-01",
        "quantity_kg": "200.00",
        "price_per_kg": "1.50000",
    })
    assert purchase.status_code == 302
    product = FeedProductModel.objects.get(farm=farm, name="Starter")
    assert FinishedFeedBatchModel.objects.get(product=product).remaining_quantity_kg == Decimal("200.00")
    serving = client.post(reverse("create_feed_serving"), {
        "product": product.pk,
        "date": "2026-07-02",
        "time": "08:00",
        "quantity_kg": "50.00",
        "note": "Sektor A",
    })
    assert serving.status_code == 302
    assert product.servings.get().quantity_kg == Decimal("50.00")
    assert FinishedFeedBatchModel.objects.get(product=product).remaining_quantity_kg == Decimal("150.00")


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
