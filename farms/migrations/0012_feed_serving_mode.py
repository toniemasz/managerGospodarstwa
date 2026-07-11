from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("farms", "0011_add_statistics_module_visibility")]
    operations = [
        migrations.AddField(
            model_name="farmsettingsmodel",
            name="feed_serving_mode",
            field=models.CharField(
                choices=[
                    ("MANUAL", "Pozostaw na magazynie"),
                    ("ASK_ON_COMPLETION", "Zapytaj przy zakończeniu"),
                    ("AUTO_FULL_PRODUCTION", "Automatycznie podaj całą produkcję"),
                ],
                default="MANUAL",
                max_length=24,
            ),
        ),
    ]
