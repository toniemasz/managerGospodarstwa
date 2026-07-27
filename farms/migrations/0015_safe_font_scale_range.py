from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("farms", "0014_default_automatic_feed_serving"),
    ]

    operations = [
        migrations.AlterField(
            model_name="farmsettingsmodel",
            name="font_scale",
            field=models.PositiveSmallIntegerField(
                default=100,
                validators=[
                    MinValueValidator(
                        80,
                        "Rozmiar tekstu nie może być mniejszy niż 80%%.",
                    ),
                    MaxValueValidator(
                        150,
                        "Rozmiar tekstu nie może być większy niż 150%%.",
                    ),
                ],
            ),
        ),
    ]
