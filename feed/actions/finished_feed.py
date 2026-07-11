from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
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
from common.money import quantize_kg, quantize_money, quantize_price
from feed.domain.exceptions import FinishedFeedInsufficientStockError
from common.cache import invalidate_farm_cache_on_commit


@transaction.atomic
def create_purchased_ready_feed_product(*, farm, name):
    if farm is None:
        raise ValueError("Utworzenie produktu gotowej paszy wymaga jawnego gospodarstwa.")

    normalized_name = name.strip()
    if not normalized_name:
        raise ValidationError("Nazwa gotowej paszy nie może być pusta.")

    # Blokada gospodarstwa serializuje tworzenie produktów również wtedy, gdy
    # równolegle kończone śrutowanie tworzy produkt na podstawie receptury.
    farm.__class__.objects.select_for_update().get(pk=farm.pk)
    if FeedProductModel.objects.filter(farm=farm, name__iexact=normalized_name).exists():
        raise ValidationError("Produkt gotowej paszy o tej nazwie już istnieje.")

    try:
        with transaction.atomic():
            product = FeedProductModel.objects.create(
                farm=farm,
                name=normalized_name,
                source_type=FeedProductModel.SourceTypes.PURCHASED_READY,
                recipe=None,
                is_active=True,
            )
    except IntegrityError as error:
        raise ValidationError("Produkt gotowej paszy o tej nazwie już istnieje.") from error

    invalidate_farm_cache_on_commit(farm, groups=("feed", "inventory"))
    return product


@transaction.atomic
def create_ready_feed_delivery(*, farm, product, date, quantity_kg, price_per_kg, user=None):
    product = FeedProductModel.objects.select_for_update().get(pk=product.pk, farm=farm)
    if product.source_type != FeedProductModel.SourceTypes.PURCHASED_READY:
        raise ValidationError("Ten produkt nie jest kupioną paszą gotową.")
    quantity = quantize_kg(quantity_kg)
    price = quantize_price(price_per_kg)
    if quantity <= 0 or price <= 0:
        raise ValidationError("Ilość i cena gotowej paszy muszą być dodatnie.")
    delivery = ReadyFeedDeliveryModel.objects.create(
        farm=farm, product=product, date=date, quantity_kg=quantity,
        price_per_kg=price, total_cost=quantize_money(quantity * price), created_by=user,
    )
    FinishedFeedBatchModel.objects.create(
        farm=farm, product=product, batch_date=date,
        initial_quantity_kg=quantity, remaining_quantity_kg=quantity,
        cost_per_kg=delivery.price_per_kg, total_cost=delivery.total_cost,
        ready_feed_delivery=delivery,
    )
    invalidate_farm_cache_on_commit(farm, groups=("feed", "inventory"))
    return delivery


def production_creates_produced_feed(production) -> bool:
    """Typ produktu wynika z procesu produkcji, a nie ze składu receptury."""
    return production.pk is not None


def create_finished_feed_batch_for_production(production):
    farm = production.recipe.farm
    farm.__class__.objects.select_for_update().get(pk=farm.pk)
    product = FeedProductModel.objects.select_for_update().filter(
        farm=farm,
        recipe=production.recipe,
        source_type=FeedProductModel.SourceTypes.PRODUCED,
    ).first()
    if product is None:
        product_name = production.recipe.name
        conflicting_product = FeedProductModel.objects.select_for_update().filter(
            farm=farm,
            name__iexact=product_name,
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
        existing = FeedServingModel.objects.filter(
            farm=farm,
            automatic_for_production=automatic_for_production,
        ).first()
        if existing:
            return existing
        if automatic_for_production.recipe.farm_id != farm.pk:
            raise ValidationError("Produkcja automatycznego podania należy do innego gospodarstwa.")
        batches = list(
            FinishedFeedBatchModel.objects.select_for_update().filter(
                farm=farm,
                product=product,
                production=automatic_for_production,
                remaining_quantity_kg__gt=0,
            )
        )
    else:
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
