from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def normalize_font_scale(apps, schema_editor):
    FarmSettingsModel = apps.get_model('farms', 'FarmSettingsModel')
    for settings in FarmSettingsModel.objects.only('id', 'font_scale'):
        try:
            scale = int(settings.font_scale or 100)
        except (TypeError, ValueError):
            scale = 100
        settings.font_scale = str(min(200, max(20, scale)))
        settings.save(update_fields=['font_scale'])


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0009_interface_theme_font_scale'),
    ]

    operations = [
        migrations.RunPython(normalize_font_scale, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='farmsettingsmodel',
            name='font_scale',
            field=models.PositiveSmallIntegerField(
                default=100,
                validators=[
                    MinValueValidator(20, 'Rozmiar tekstu nie może być mniejszy niż 20%%.'),
                    MaxValueValidator(200, 'Rozmiar tekstu nie może być większy niż 200%%.'),
                ],
            ),
        ),
    ]
