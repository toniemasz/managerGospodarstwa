import django.db.models.functions.text
from django.db import migrations, models


def normalize_category_names(apps, schema_editor):
    Category = apps.get_model('costs', 'CostCategoryModel')
    used_by_farm = {}
    for category in Category.objects.order_by('farm_id', 'id').iterator():
        used = used_by_farm.setdefault(category.farm_id, set())
        base = category.name.strip()
        candidate = base
        suffix_number = 0
        while candidate.lower() in used:
            suffix_number += 1
            suffix = f" ({suffix_number})"
            candidate = f"{base[:100 - len(suffix)].rstrip()}{suffix}"
        used.add(candidate.lower())
        if candidate != category.name:
            Category.objects.filter(pk=category.pk).update(name=candidate)


class Migration(migrations.Migration):
    dependencies = [
        ('costs', '0005_protect_production_cost'),
        ('farms', '0014_default_automatic_feed_serving'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='costcategorymodel',
            name='unique_cost_category_name_per_farm',
        ),
        migrations.RunPython(normalize_category_names, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='costcategorymodel',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('name')
                ),
                models.F('farm'),
                name='unique_cost_category_name_per_farm_ci',
            ),
        ),
    ]
