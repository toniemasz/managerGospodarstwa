from django.db import migrations, models


def add_archive_columns_if_missing(apps, schema_editor):
    sow_model = apps.get_model('sows', 'SowModel')
    table_name = sow_model._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }

    fields = [
        ('is_archived', models.BooleanField(default=False, verbose_name='Czy zarchiwizowana?')),
        ('archived_at', models.DateTimeField(blank=True, null=True)),
    ]

    for field_name, field in fields:
        if field_name in existing_columns:
            continue

        field.set_attributes_from_name(field_name)
        definition, params = schema_editor.column_sql(sow_model, field, include_default=True)
        schema_editor.execute(
            f"ALTER TABLE {schema_editor.quote_name(table_name)} "
            f"ADD COLUMN {schema_editor.quote_name(field_name)} {definition}",
            params,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('sows', '0003_vaccinationplanmodel_days_after_event_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    add_archive_columns_if_missing,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='sowmodel',
                    name='archived_at',
                    field=models.DateTimeField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='sowmodel',
                    name='is_archived',
                    field=models.BooleanField(default=False, verbose_name='Czy zarchiwizowana?'),
                ),
            ],
        ),
    ]
