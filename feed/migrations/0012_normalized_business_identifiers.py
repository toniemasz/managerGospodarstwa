from decimal import Decimal

import django.db.models.functions.text
from django.db import migrations, models


def _next_unique_value(value, used, max_length):
    base = value.strip()
    candidate = base
    suffix_number = 0
    while candidate.lower() in used:
        suffix_number += 1
        suffix = f" ({suffix_number})"
        candidate = f"{base[:max_length - len(suffix)].rstrip()}{suffix}"
    used.add(candidate.lower())
    return candidate


def normalize_feed_identifiers(apps, schema_editor):
    definitions = (
        ('IngredientModel', 100),
        ('RecipeModel', 150),
        ('FeedProductModel', 150),
    )
    for model_name, max_length in definitions:
        Model = apps.get_model('feed', model_name)
        used_by_farm = {}
        for obj in Model.objects.order_by('farm_id', 'id').iterator():
            used = used_by_farm.setdefault(obj.farm_id, set())
            candidate = _next_unique_value(obj.name, used, max_length)
            if candidate != obj.name:
                Model.objects.filter(pk=obj.pk).update(name=candidate)

    RecipeItem = apps.get_model('feed', 'RecipeItemModel')
    first_items = {}
    for item in RecipeItem.objects.order_by('recipe_id', 'ingredient_id', 'id').iterator():
        key = (item.recipe_id, item.ingredient_id)
        first = first_items.get(key)
        if first is None:
            first_items[key] = item
            continue
        first.percentage = Decimal(first.percentage) + Decimal(item.percentage)
        RecipeItem.objects.filter(pk=first.pk).update(percentage=first.percentage)
        RecipeItem.objects.filter(pk=item.pk).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('farms', '0014_default_automatic_feed_serving'),
        ('feed', '0011_protect_production_dependencies'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='feedproductmodel',
            name='unique_feed_product_name_per_farm',
        ),
        migrations.RemoveConstraint(
            model_name='ingredientmodel',
            name='unique_ingredient_name_per_farm',
        ),
        migrations.RemoveConstraint(
            model_name='recipemodel',
            name='unique_recipe_name_per_farm',
        ),
        migrations.RunPython(normalize_feed_identifiers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='feedproductmodel',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('name')
                ),
                models.F('farm'),
                name='unique_feed_product_name_per_farm_ci',
            ),
        ),
        migrations.AddConstraint(
            model_name='ingredientmodel',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('name')
                ),
                models.F('farm'),
                name='unique_ingredient_name_per_farm_ci',
            ),
        ),
        migrations.AddConstraint(
            model_name='recipeitemmodel',
            constraint=models.UniqueConstraint(
                fields=('recipe', 'ingredient'),
                name='unique_ingredient_per_recipe',
            ),
        ),
        migrations.AddConstraint(
            model_name='recipemodel',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('name')
                ),
                models.F('farm'),
                name='unique_recipe_name_per_farm_ci',
            ),
        ),
    ]
