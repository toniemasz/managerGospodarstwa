from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from feed.models import (
    FeedProductModel,
    FeedServingAllocationModel,
    FeedServingModel,
    FinishedFeedBatchModel,
    ProductionModel,
    ReadyFeedDeliveryModel,
)
from common.units import format_mass
from common.money import quantize_money, quantize_price
from feed.domain.exceptions import FinishedFeedInsufficientStockError
from common.cache import invalidate_farm_cache_on_commit


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
        price_per_kg=quantize_price(price), total_cost=quantize_money(quantity * price), created_by=user,
    )
    FinishedFeedBatchModel.objects.create(
        farm=farm, product=product, batch_date=date,
        initial_quantity_kg=quantity, remaining_quantity_kg=quantity,
        cost_per_kg=price, total_cost=delivery.total_cost,
        ready_feed_delivery=delivery,
    )
    invalidate_farm_cache_on_commit(farm, groups=("feed", "inventory"))
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


def production_creates_produced_feed(production) -> bool:
    """Typ produktu wynika z procesu produkcji, a nie ze składu receptury."""
    return production.pk is not None


def create_finished_feed_batch_for_production(production):
    farm = production.recipe.farm
    product = FeedProductModel.objects.select_for_update().filter(
        farm=farm,
        recipe=production.recipe,
        source_type=FeedProductModel.SourceTypes.PRODUCED,
    ).first()
    if product is None:
        product_name = production.recipe.name
        conflicting_product = FeedProductModel.objects.select_for_update().filter(
            farm=farm,
            name=product_name,
        ).first()
        if conflicting_product is not None and conflicting_product.source_type != FeedProductModel.SourceTypes.PRODUCED:
            product_name = f"{product_name} (produkcja)"
        product, _ = FeedProductModel.objects.get_or_create(
            farm=farm,
            name=product_name,
            defaults={
                "recipe": production.recipe,
                "source_type": FeedProductModel.SourceTypes.PRODUCED,
            },
        )
    if product.source_type != FeedProductModel.SourceTypes.PRODUCED:
        raise ValidationError("Produkt produkcji nie może być sklasyfikowany jako pasza kupiona.")
    if product.recipe_id != production.recipe_id:
        raise ValidationError("Produkt produkowany jest powiązany z inną recepturą.")
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
    if batch.product_id != product.pk:
        raise ValidationError("Istniejąca partia produkcji wskazuje inny produkt.")
    batch_updates = {
        "batch_date": production.date,
        "cost_per_kg": production.feed_cost_per_kg,
        "total_cost": production.feed_cost_total,
        "cost_is_partial": production.feed_cost_is_partial,
    }
    for field, value in batch_updates.items():
        setattr(batch, field, value)
    batch.save(update_fields=tuple(batch_updates))
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
        raise FinishedFeedInsufficientStockError(
            f"Brak gotowej paszy. Dostępne: {format_mass(available)}."
        )
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
        cost = quantize_money(allocated * batch.cost_per_kg)
        FeedServingAllocationModel.objects.create(
            serving=serving, batch=batch, quantity_kg=allocated,
            unit_cost=batch.cost_per_kg, cost=cost,
        )
        FinishedFeedBatchModel.objects.filter(pk=batch.pk).update(
            remaining_quantity_kg=F("remaining_quantity_kg") - allocated,
        )
        remaining -= allocated
        total_cost += cost
    serving.total_cost = quantize_money(total_cost)
    serving.save(update_fields=("total_cost",))
    invalidate_farm_cache_on_commit(farm, groups=("feed", "inventory"))
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
    invalidate_farm_cache_on_commit(farm, groups=("feed", "inventory"))
