from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations
from django.db.models import Sum


KG = Decimal("0.01")
MONEY = Decimal("0.01")
PRICE = Decimal("0.00001")


def quantize(value, quantum):
    return Decimal(value or 0).quantize(quantum, rounding=ROUND_HALF_UP)


def production_items(RecipeItem, RecipeVersionItem, production):
    if production.recipe_version_id:
        version_items = list(
            RecipeVersionItem.objects.filter(recipe_version_id=production.recipe_version_id)
            .order_by("ingredient_id", "id")
        )
        if version_items:
            return version_items
    return list(RecipeItem.objects.filter(recipe_id=production.recipe_id).order_by("ingredient_id", "id"))


def calculate_historical_cost(Delivery, Usage, items, production):
    usages = Usage.objects.filter(production_id=production.pk)
    if usages.exists():
        total = usages.aggregate(total=Sum("cost"))["total"] or Decimal("0.00")
        if total <= 0 and production.feed_cost_total > 0:
            total = production.feed_cost_total
        partial = usages.filter(delivery__isnull=True).exists() or usages.filter(unit_price__lte=0).exists()
        return quantize(total, MONEY), partial, "Koszt historyczny odtworzony z rozliczeń FIFO."

    custom = production.custom_recipe_data or {}
    total = Decimal("0.00")
    missing = []
    for item in items:
        percentage = Decimal(str(custom.get(str(item.ingredient_id), item.percentage)))
        quantity = quantize(production.quantity_kg * percentage / Decimal("100"), KG)
        delivery = (
            Delivery.objects.filter(
                ingredient_id=item.ingredient_id,
                date__lte=production.date,
                price_per_kg__isnull=False,
                price_per_kg__gt=0,
            )
            .order_by("-date", "-id")
            .first()
        )
        if delivery is None:
            delivery = (
                Delivery.objects.filter(
                    ingredient_id=item.ingredient_id,
                    price_per_kg__isnull=False,
                    price_per_kg__gt=0,
                )
                .order_by("date", "id")
                .first()
            )
        if delivery is None:
            missing.append(str(item.ingredient_id))
            continue
        total += quantity * delivery.price_per_kg
    partial = bool(missing)
    note = "Koszt historyczny odtworzony z cen dostaw."
    if missing:
        note = "Częściowy koszt historyczny - brak ceny składników: " + ", ".join(missing)
    return quantize(total, MONEY), partial, note


def backfill_finished_feed_history(apps, schema_editor):
    Production = apps.get_model("feed", "ProductionModel")
    RecipeItem = apps.get_model("feed", "RecipeItemModel")
    RecipeVersionItem = apps.get_model("feed", "RecipeVersionItemModel")
    Delivery = apps.get_model("feed", "DeliveryModel")
    Usage = apps.get_model("feed", "ProductionIngredientUsageModel")
    Product = apps.get_model("feed", "FeedProductModel")
    Batch = apps.get_model("feed", "FinishedFeedBatchModel")
    Serving = apps.get_model("feed", "FeedServingModel")
    Allocation = apps.get_model("feed", "FeedServingAllocationModel")

    productions = (
        Production.objects.filter(status="COMPLETED")
        .select_related("recipe", "recipe_version")
        .order_by("date", "time", "id")
    )
    for production in productions.iterator():
        farm_id = production.recipe.farm_id
        items = production_items(RecipeItem, RecipeVersionItem, production)
        is_ready_feed = len(items) == 1
        source_type = "PURCHASED_READY" if is_ready_feed else "PRODUCED"

        product = Product.objects.filter(farm_id=farm_id, name=production.recipe.name).first()
        if product is None:
            product = Product.objects.create(
                farm_id=farm_id,
                name=production.recipe.name,
                source_type=source_type,
                recipe_id=production.recipe_id,
                is_active=True,
            )
        else:
            updates = {}
            if product.source_type != source_type:
                updates["source_type"] = source_type
            if product.recipe_id is None:
                updates["recipe_id"] = production.recipe_id
            if updates:
                Product.objects.filter(pk=product.pk).update(**updates)
                for name, value in updates.items():
                    setattr(product, name, value)

        if items:
            total_cost, partial, cost_note = calculate_historical_cost(
                Delivery, Usage, items, production
            )
        else:
            total_cost = quantize(production.feed_cost_total, MONEY)
            partial = True
            cost_note = "Częściowy koszt historyczny - receptura nie ma zapisanego składu."
        cost_per_kg = Decimal("0.00000")
        if production.quantity_kg:
            cost_per_kg = quantize(total_cost / production.quantity_kg, PRICE)
        Production.objects.filter(pk=production.pk).update(
            feed_cost_total=total_cost,
            feed_cost_per_kg=cost_per_kg,
            feed_cost_is_partial=partial,
            feed_cost_note=cost_note[:255],
            completion_feed_serving_mode="AUTO_FULL_PRODUCTION" if is_ready_feed else "MANUAL",
        )

        batch = Batch.objects.filter(production_id=production.pk).first()
        batch_created = batch is None
        if batch is None:
            batch = Batch.objects.create(
                farm_id=farm_id,
                product_id=product.pk,
                batch_date=production.date,
                initial_quantity_kg=production.quantity_kg,
                remaining_quantity_kg=production.quantity_kg,
                cost_per_kg=cost_per_kg,
                total_cost=total_cost,
                cost_is_partial=partial,
                production_id=production.pk,
            )

        if not is_ready_feed:
            continue
        if not batch_created and Allocation.objects.filter(batch_id=batch.pk).exists():
            continue
        serving = Serving.objects.filter(automatic_for_production_id=production.pk).first()
        if serving is None:
            serving = Serving.objects.create(
                farm_id=farm_id,
                product_id=product.pk,
                date=production.date,
                time=production.time,
                quantity_kg=production.quantity_kg,
                note="Historyczne podanie jednoskładnikowej gotowej paszy.",
                total_cost=total_cost,
                is_automatic=True,
                automatic_for_production_id=production.pk,
            )
        allocation = Allocation.objects.filter(serving_id=serving.pk, batch_id=batch.pk).first()
        if allocation is None:
            Allocation.objects.create(
                serving_id=serving.pk,
                batch_id=batch.pk,
                quantity_kg=production.quantity_kg,
                unit_cost=cost_per_kg,
                cost=total_cost,
            )
        Batch.objects.filter(pk=batch.pk).update(remaining_quantity_kg=Decimal("0.00"))


class Migration(migrations.Migration):
    dependencies = [("feed", "0007_finished_feed_inventory")]
    operations = [
        migrations.RunPython(backfill_finished_feed_history, migrations.RunPython.noop),
    ]
