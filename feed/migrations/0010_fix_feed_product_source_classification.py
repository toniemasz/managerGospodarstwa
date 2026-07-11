from django.db import migrations, models


def _available_name(Product, farm_id, base_name):
    suffix = " (produkcja)"
    candidate = f"{base_name[:150 - len(suffix)]}{suffix}"
    index = 2
    while Product.objects.filter(farm_id=farm_id, name=candidate).exists():
        numbered_suffix = f" (produkcja {index})"
        candidate = f"{base_name[:150 - len(numbered_suffix)]}{numbered_suffix}"
        index += 1
    return candidate


def fix_source_classification(apps, schema_editor):
    Product = apps.get_model("feed", "FeedProductModel")
    Batch = apps.get_model("feed", "FinishedFeedBatchModel")

    for product in Product.objects.all().order_by("farm_id", "id").iterator():
        production_batches = Batch.objects.filter(product_id=product.pk, production_id__isnull=False)
        purchased_batches = Batch.objects.filter(product_id=product.pk, ready_feed_delivery_id__isnull=False)
        has_production = production_batches.exists()
        has_purchase = purchased_batches.exists()
        if has_production and has_purchase:
            first_production_batch = production_batches.select_related("production__recipe").order_by("id").first()
            produced_product = Product.objects.create(
                farm_id=product.farm_id,
                name=_available_name(Product, product.farm_id, product.name),
                source_type="PRODUCED",
                recipe_id=first_production_batch.production.recipe_id,
                source_classification_conflict=True,
                is_active=product.is_active,
            )
            production_batches.update(product_id=produced_product.pk)
            Product.objects.filter(pk=product.pk).update(
                source_type="PURCHASED_READY",
                source_classification_conflict=True,
            )
        elif has_production:
            first_batch = production_batches.select_related("production__recipe").order_by("id").first()
            Product.objects.filter(pk=product.pk).update(
                source_type="PRODUCED",
                recipe_id=first_batch.production.recipe_id,
            )
        elif has_purchase:
            Product.objects.filter(pk=product.pk).update(source_type="PURCHASED_READY")


class Migration(migrations.Migration):
    dependencies = [("feed", "0009_backfill_automatic_feed_servings")]

    operations = [
        migrations.AddField(
            model_name="feedproductmodel",
            name="source_classification_conflict",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(fix_source_classification, migrations.RunPython.noop),
    ]
