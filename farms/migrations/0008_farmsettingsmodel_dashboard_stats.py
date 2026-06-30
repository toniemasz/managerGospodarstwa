import farms.dashboard_registry
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0007_farmsettingsmodel_nav_modules'),
    ]

    operations = [
        migrations.AddField(
            model_name='farmsettingsmodel',
            name='dashboard_stats',
            field=models.JSONField(blank=True, default=farms.dashboard_registry.default_dashboard_stats),
        ),
        migrations.AddField(
            model_name='farmsettingsmodel',
            name='interface_scale',
            field=models.CharField(choices=[('compact', 'Kompaktowy'), ('comfortable', 'Wygodny'), ('large', 'Powiększony')], default='compact', max_length=16),
        ),
    ]
