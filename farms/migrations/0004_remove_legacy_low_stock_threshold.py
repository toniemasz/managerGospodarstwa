from django.db import migrations


def remove_legacy_column_if_present(apps, schema_editor):
    FarmSettingsModel = apps.get_model('farms', 'FarmSettingsModel')
    table_name = FarmSettingsModel._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    if 'low_stock_threshold_kg' in columns:
        schema_editor.remove_field(
            FarmSettingsModel,
            FarmSettingsModel._meta.get_field('low_stock_threshold_kg'),
        )


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0003_farmsettingsmodel'),
        ('feed', '0003_ingredient_low_stock_threshold'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    remove_legacy_column_if_present,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.RemoveField(
                    model_name='farmsettingsmodel',
                    name='low_stock_threshold_kg',
                ),
            ],
        ),
    ]
