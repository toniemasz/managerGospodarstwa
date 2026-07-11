from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


FEED_CATEGORY_NAME = "Pasza"
FEED_CATEGORY_DESCRIPTION = "Automatyczne koszty zakończonych śrutowań rozliczone według FIFO."


def backfill_production_costs(apps, schema_editor):
    Category = apps.get_model("costs", "CostCategoryModel")
    Cost = apps.get_model("costs", "CostModel")
    Production = apps.get_model("feed", "ProductionModel")

    categories = {}
    productions = Production.objects.filter(status="COMPLETED").select_related("recipe").order_by("date", "time", "id")
    for production in productions.iterator():
        farm_id = production.recipe.farm_id
        category = categories.get(farm_id)
        if category is None:
            category = Category.objects.filter(
                farm_id=farm_id,
                name__iexact=FEED_CATEGORY_NAME,
            ).first()
            if category is None:
                category = Category.objects.create(
                    farm_id=farm_id,
                    name=FEED_CATEGORY_NAME,
                    description=FEED_CATEGORY_DESCRIPTION,
                    is_active=True,
                )
            if not category.is_active:
                Category.objects.filter(pk=category.pk).update(is_active=True)
            categories[farm_id] = category
        amount = Decimal(production.feed_cost_total or 0).quantize(Decimal("0.01"))
        Cost.objects.update_or_create(
            production_id=production.pk,
            defaults={
                "farm_id": farm_id,
                "category_id": category.pk,
                "date": production.date,
                "amount": amount,
                "description": f"Pasza – śrutowanie {production.recipe.name} ({production.quantity_kg:.2f} kg)",
                "document_number": f"ŚRUTOWANIE/{production.pk}",
                "supplier": "",
                "is_paid": True,
                "created_by_id": None,
            },
        )


def remove_production_costs(apps, schema_editor):
    Cost = apps.get_model("costs", "CostModel")
    Cost.objects.filter(production__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("costs", "0001_initial"),
        ("feed", "0009_backfill_automatic_feed_servings"),
    ]
    operations = [
        migrations.AddField(
            model_name="costmodel",
            name="production",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="cost_entry",
                to="feed.productionmodel",
                verbose_name="Śrutowanie źródłowe",
            ),
        ),
        migrations.AlterField(
            model_name="costmodel",
            name="amount",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=14,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Kwota",
            ),
        ),
        migrations.RunPython(backfill_production_costs, remove_production_costs),
    ]
