from django.db import migrations, models


def enable_automatic_feed_serving(apps, schema_editor):
    FarmSettings = apps.get_model("farms", "FarmSettingsModel")
    FarmSettings.objects.exclude(feed_serving_mode="AUTO_FULL_PRODUCTION").update(
        feed_serving_mode="AUTO_FULL_PRODUCTION",
    )


class Migration(migrations.Migration):
    dependencies = [("farms", "0013_backupimportpreviewmodel")]
    operations = [
        migrations.AlterField(
            model_name="farmsettingsmodel",
            name="feed_serving_mode",
            field=models.CharField(
                choices=[
                    ("MANUAL", "Pozostaw na magazynie"),
                    ("ASK_ON_COMPLETION", "Zapytaj przy zakończeniu"),
                    ("AUTO_FULL_PRODUCTION", "Automatycznie podaj całą produkcję"),
                ],
                default="AUTO_FULL_PRODUCTION",
                max_length=24,
            ),
        ),
        migrations.RunPython(enable_automatic_feed_serving, migrations.RunPython.noop),
    ]
