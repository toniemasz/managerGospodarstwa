from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0006_normalized_document_identifiers"),
    ]

    operations = [
        migrations.AddField(
            model_name="pigsalemodel",
            name="settlement_review_required",
            field=models.BooleanField(
                default=False,
                verbose_name="Import wymaga sprawdzenia",
            ),
        ),
    ]
