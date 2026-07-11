import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("feed", "0010_fix_feed_product_source_classification")]

    operations = [
        migrations.AlterField(
            model_name="finishedfeedbatchmodel",
            name="production",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="finished_feed_batch",
                to="feed.productionmodel",
            ),
        ),
        migrations.AlterField(
            model_name="feedservingmodel",
            name="automatic_for_production",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.RESTRICT,
                related_name="automatic_feed_serving",
                to="feed.productionmodel",
            ),
        ),
    ]
