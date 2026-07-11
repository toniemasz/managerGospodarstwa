from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


def _number(value, decimals):
    quantum = Decimal("1").scaleb(-decimals)
    rounded = Decimal(value).quantize(quantum, rounding=ROUND_HALF_UP)
    text = format(rounded, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def refresh_feed_cost_descriptions(apps, schema_editor):
    Cost = apps.get_model("costs", "CostModel")
    costs = Cost.objects.filter(production__isnull=False).select_related("production__recipe")
    for cost in costs.iterator():
        quantity_kg = Decimal(cost.production.quantity_kg)
        if abs(quantity_kg) >= Decimal("1000"):
            mass = f"{_number(quantity_kg / Decimal('1000'), 5)} t"
        else:
            mass = f"{_number(quantity_kg, 2)} kg"
        Cost.objects.filter(pk=cost.pk).update(
            description=f"Pasza – śrutowanie {cost.production.recipe.name} ({mass})",
        )


class Migration(migrations.Migration):
    dependencies = [("costs", "0003_format_feed_cost_mass_units")]
    operations = [
        migrations.RunPython(refresh_feed_cost_descriptions, migrations.RunPython.noop),
    ]
