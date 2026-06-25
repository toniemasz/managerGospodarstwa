from django.db import migrations, models

import farms.module_registry


class Migration(migrations.Migration):
    dependencies = [
        ("farms", "0005_auditlogmodel"),
    ]

    operations = [
        migrations.AddField(
            model_name="farmsettingsmodel",
            name="visible_modules",
            field=models.JSONField(
                blank=True,
                default=farms.module_registry.default_visible_modules,
            ),
        ),
    ]
