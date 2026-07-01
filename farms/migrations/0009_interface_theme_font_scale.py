from django.db import migrations, models


def normalize_interface_scale(apps, schema_editor):
    FarmSettingsModel = apps.get_model('farms', 'FarmSettingsModel')
    FarmSettingsModel.objects.filter(interface_scale='large').update(interface_scale='comfortable')


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0008_farmsettingsmodel_dashboard_stats'),
    ]

    operations = [
        migrations.AlterField(
            model_name='farmsettingsmodel',
            name='interface_scale',
            field=models.CharField(
                choices=[
                    ('compact', 'Kompaktowy'),
                    ('standard', 'Standardowy'),
                    ('comfortable', 'Wygodny'),
                ],
                default='standard',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='farmsettingsmodel',
            name='theme',
            field=models.CharField(
                choices=[
                    ('light', 'Jasny'),
                    ('dark', 'Ciemny'),
                    ('system', 'Systemowy'),
                ],
                default='light',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='farmsettingsmodel',
            name='font_scale',
            field=models.CharField(
                choices=[
                    ('100', '100%'),
                    ('110', '110%'),
                    ('125', '125%'),
                    ('150', '150%'),
                    ('175', '175%'),
                    ('200', '200%'),
                ],
                default='100',
                max_length=8,
            ),
        ),
        migrations.RunPython(normalize_interface_scale, migrations.RunPython.noop),
    ]
