from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum

from feed.models import (
    FeedProductModel,
    FeedServingAllocationModel,
    FeedServingModel,
    FinishedFeedBatchModel,
    ProductionModel,
    ReadyFeedDeliveryModel,
)
from feed.selectors.recipe_requirements import recipe_item_dicts_for_production
from common.units import format_mass


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def create_ready_feed_delivery(*, farm, product, date, quantity_kg, price_per_kg, user=None):
    product = FeedProductModel.objects.select_for_update().get(pk=product.pk, farm=farm)
    if product.source_type != FeedProductModel.SourceTypes.PURCHASED_READY:
        raise ValidationError("Ten produkt nie jest kupioną paszą gotową.")
    quantity = Decimal(quantity_kg)
    price = Decimal(price_per_kg)
    if quantity <= 0 or price <= 0:
        raise ValidationError("Ilość i cena gotowej paszy muszą być dodatnie.")
    delivery = ReadyFeedDeliveryModel.objects.create(
        farm=farm, product=product, date=date, quantity_kg=quantity,
        price_per_kg=price, total_cost=_money(quantity * price), created_by=user,
    )
    FinishedFeedBatchModel.objects.create(
        farm=farm, product=product, batch_date=date,
        initial_quantity_kg=quantity, remaining_quantity_kg=quantity,
        cost_per_kg=price, total_cost=delivery.total_cost,
        ready_feed_delivery=delivery,
    )
    return delivery


@transaction.atomic
def purchase_ready_feed(*, farm, product_name, date, quantity_kg, price_per_kg, user=None):
    product, _ = FeedProductModel.objects.select_for_update().get_or_create(
        farm=farm,
        name=product_name.strip(),
        defaults={"source_type": FeedProductModel.SourceTypes.PURCHASED_READY},
    )
    if product.source_type != FeedProductModel.SourceTypes.PURCHASED_READY:
        raise ValidationError("Produkt o tej nazwie jest powiązany z produkowaną paszą.")
    return create_ready_feed_delivery(
        farm=farm,
        product=product,
        date=date,
        quantity_kg=quantity_kg,
        price_per_kg=price_per_kg,
        user=user,
    )


def production_is_ready_feed(production):
    return len(recipe_item_dicts_for_production(production)) == 1


def create_finished_feed_batch_for_production(production):
    source_type = (
        FeedProductModel.SourceTypes.PURCHASED_READY
        if production_is_ready_feed(production)
        else FeedProductModel.SourceTypes.PRODUCED
    )
    product, _ = FeedProductModel.objects.get_or_create(
        farm=production.recipe.farm,
        name=production.recipe.name,
        defaults={
            "recipe": production.recipe,
            "source_type": source_type,
        },
    )
    product_updates = {}
    if product.recipe_id is None:
        product_updates["recipe"] = production.recipe
    if product.source_type != source_type:
        product_updates["source_type"] = source_type
    if product_updates:
        FeedProductModel.objects.filter(pk=product.pk).update(**product_updates)
        for name, value in product_updates.items():
            setattr(product, name, value)
    batch, _ = FinishedFeedBatchModel.objects.get_or_create(
        production=production,
        defaults={
            "farm": production.recipe.farm,
            "product": product,
            "batch_date": production.date,
            "initial_quantity_kg": production.quantity_kg,
            "remaining_quantity_kg": production.quantity_kg,
            "cost_per_kg": production.feed_cost_per_kg,
            "total_cost": production.feed_cost_total,
            "cost_is_partial": production.feed_cost_is_partial,
        },
    )
    return batch


@transaction.atomic
def create_feed_serving(*, farm, product, date, quantity_kg, user=None, note="", time=None, automatic_for_production=None):
    product = FeedProductModel.objects.select_for_update().get(pk=product.pk, farm=farm)
    quantity = Decimal(quantity_kg)
    if quantity <= 0:
        raise ValidationError("Ilość podania musi być dodatnia.")
    if automatic_for_production:
        existing = FeedServingModel.objects.filter(automatic_for_production=automatic_for_production).first()
        if existing:
            return existing
    batches = list(
        FinishedFeedBatchModel.objects.select_for_update()
        .filter(farm=farm, product=product, batch_date__lte=date, remaining_quantity_kg__gt=0)
        .order_by("batch_date", "id")
    )
    available = sum((batch.remaining_quantity_kg for batch in batches), Decimal("0.00"))
    if quantity > available:
        raise ValidationError(f"Brak gotowej paszy. Dostępne: {format_mass(available)}.")
    serving = FeedServingModel.objects.create(
        farm=farm, product=product, date=date, time=time, quantity_kg=quantity, note=note,
        is_automatic=automatic_for_production is not None,
        automatic_for_production=automatic_for_production, created_by=user,
    )
    remaining = quantity
    total_cost = Decimal("0.00")
    for batch in batches:
        if remaining <= 0:
            break
        allocated = min(batch.remaining_quantity_kg, remaining)
        cost = _money(allocated * batch.cost_per_kg)
        FeedServingAllocationModel.objects.create(
            serving=serving, batch=batch, quantity_kg=allocated,
            unit_cost=batch.cost_per_kg, cost=cost,
        )
        FinishedFeedBatchModel.objects.filter(pk=batch.pk).update(
            remaining_quantity_kg=F("remaining_quantity_kg") - allocated,
        )
        remaining -= allocated
        total_cost += cost
    serving.total_cost = _money(total_cost)
    serving.save(update_fields=("total_cost",))
    return serving


@transaction.atomic
def delete_feed_serving(*, farm, serving):
    serving = FeedServingModel.objects.select_for_update().get(pk=serving.pk, farm=farm)
    allocations = list(serving.allocations.select_for_update().select_related("batch"))
    for allocation in allocations:
        FinishedFeedBatchModel.objects.filter(pk=allocation.batch_id).update(
            remaining_quantity_kg=F("remaining_quantity_kg") + allocation.quantity_kg,
        )
    serving.delete()
