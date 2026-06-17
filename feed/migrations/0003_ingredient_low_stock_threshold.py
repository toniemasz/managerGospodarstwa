from decimal import Decimal

import django.core.validators
from django.db import migrations, models


DEFAULT_LOW_STOCK_THRESHOLD_KG = Decimal('500')


def copy_farm_thresholds_to_ingredients(apps, schema_editor):
    IngredientModel = apps.get_model('feed', 'IngredientModel')
    FarmSettingsModel = apps.get_model('farms', 'FarmSettingsModel')

    table_name = FarmSettingsModel._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    if 'low_stock_threshold_kg' in columns:
        thresholds_by_farm_id = dict(
            FarmSettingsModel.objects.values_list('farm_id', 'low_stock_threshold_kg')
        )
    else:
        thresholds_by_farm_id = {}

    for ingredient in IngredientModel.objects.all():
        threshold = thresholds_by_farm_id.get(ingredient.farm_id, DEFAULT_LOW_STOCK_THRESHOLD_KG)
        ingredient.low_stock_threshold_kg = threshold
        ingredient.save(update_fields=['low_stock_threshold_kg'])


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0003_farmsettingsmodel'),
        ('feed', '0002_farm_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='ingredientmodel',
            name='low_stock_threshold_kg',
            field=models.DecimalField(
                decimal_places=2,
                default=DEFAULT_LOW_STOCK_THRESHOLD_KG,
                help_text='Alert pojawi się, gdy stan tego składnika spadnie poniżej tej wartości.',
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                verbose_name='Próg niskiego stanu (kg)',
            ),
        ),
        migrations.RunPython(copy_farm_thresholds_to_ingredients, migrations.RunPython.noop),
    ]
