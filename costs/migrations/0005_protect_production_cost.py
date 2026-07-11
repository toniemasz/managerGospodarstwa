import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("feed", "0011_protect_production_dependencies"),
        ("costs", "0004_refresh_feed_cost_mass_units"),
    ]

    operations = [
        migrations.AlterField(
            model_name="costmodel",
            name="production",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="cost_entry",
                to="feed.productionmodel",
                verbose_name="Śrutowanie źródłowe",
            ),
        ),
    ]
