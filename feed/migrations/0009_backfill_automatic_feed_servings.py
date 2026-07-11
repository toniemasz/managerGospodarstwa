from decimal import Decimal

from django.db import migrations


def backfill_automatic_feed_servings(apps, schema_editor):
    Production = apps.get_model("feed", "ProductionModel")
    Batch = apps.get_model("feed", "FinishedFeedBatchModel")
    Serving = apps.get_model("feed", "FeedServingModel")
    Allocation = apps.get_model("feed", "FeedServingAllocationModel")

    productions = (
        Production.objects.filter(status="COMPLETED", automatic_feed_serving__isnull=True)
        .select_related("recipe")
        .order_by("date", "time", "id")
    )
    for production in productions.iterator():
        batch = Batch.objects.filter(production_id=production.pk).first()
        if batch is None:
            continue

        # Nie dublujemy rozchodu partii, która ma już ręczne lub automatyczne alokacje.
        if Allocation.objects.filter(batch_id=batch.pk).exists():
            continue
        if batch.remaining_quantity_kg != batch.initial_quantity_kg:
            continue

        serving = Serving.objects.create(
            farm_id=batch.farm_id,
            product_id=batch.product_id,
            date=production.date,
            time=production.time,
            quantity_kg=batch.initial_quantity_kg,
            note="Historyczne podanie paszy bezpośrednio po śrutowaniu.",
            total_cost=batch.total_cost,
            is_automatic=True,
            automatic_for_production_id=production.pk,
        )
        Allocation.objects.create(
            serving_id=serving.pk,
            batch_id=batch.pk,
            quantity_kg=batch.initial_quantity_kg,
            unit_cost=batch.cost_per_kg,
            cost=batch.total_cost,
        )
        Batch.objects.filter(pk=batch.pk).update(remaining_quantity_kg=Decimal("0.00"))
        Production.objects.filter(pk=production.pk).update(
            completion_feed_serving_mode="AUTO_FULL_PRODUCTION",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("farms", "0014_default_automatic_feed_serving"),
        ("feed", "0008_backfill_finished_feed_history"),
    ]
    operations = [
        migrations.RunPython(backfill_automatic_feed_servings, migrations.RunPython.noop),
    ]
