# Generated manually to avoid interactive auto_now_add prompt for existing events.

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('sows', '0006_require_farm'),
    ]

    operations = [
        migrations.AddField(
            model_name='sowmodel',
            name='archive_reason',
            field=models.CharField(
                choices=[
                    ('manual', 'Ręczna archiwizacja'),
                    ('death', 'Upadek'),
                ],
                default='manual',
                max_length=20,
                verbose_name='Powód archiwizacji',
            ),
        ),
        migrations.AddField(
            model_name='sowmodel',
            name='death_date',
            field=models.DateField(blank=True, null=True, verbose_name='Data upadku'),
        ),
        migrations.AddField(
            model_name='sowmodel',
            name='death_note',
            field=models.TextField(blank=True, verbose_name='Notatka o upadku'),
        ),
        migrations.AlterField(
            model_name='soweventmodel',
            name='event_type',
            field=models.CharField(
                choices=[
                    ('INSEMINATION', 'Inseminacja'),
                    ('PREGNANCY_CHECK', 'Badanie'),
                    ('FARROWING', 'Oproszenie'),
                    ('WEANING', 'Odsadzenie'),
                    ('MISCARRIAGE', 'Poronienie'),
                    ('VACCINATION', 'Szczepienie'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='soweventmodel',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name='MortalityReportModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mortality_type', models.CharField(
                    choices=[
                        ('sow', 'Maciora'),
                        ('post_weaning', 'Zwierzęta po odsadzeniu'),
                    ],
                    max_length=20,
                    verbose_name='Typ upadku',
                )),
                ('mortality_date', models.DateField(verbose_name='Data upadku')),
                ('quantity', models.PositiveIntegerField(
                    validators=[django.core.validators.MinValueValidator(1)],
                    verbose_name='Liczba sztuk',
                )),
                ('reason', models.CharField(blank=True, max_length=200, verbose_name='Przyczyna')),
                ('note', models.TextField(blank=True, verbose_name='Notatka')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Utworzono')),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='sow_mortality_reports',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Utworzył',
                )),
                ('farm', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mortality_reports',
                    to='farms.farmmodel',
                    verbose_name='Gospodarstwo',
                )),
                ('sow', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='mortality_reports',
                    to='sows.sowmodel',
                    verbose_name='Maciora',
                )),
            ],
            options={
                'verbose_name': 'Zgłoszenie upadku',
                'verbose_name_plural': 'Zgłoszenia upadków',
                'ordering': ('-mortality_date', '-created_at', '-id'),
            },
        ),
        migrations.AddIndex(
            model_name='mortalityreportmodel',
            index=models.Index(fields=['farm', '-mortality_date'], name='mortality_farm_date_idx'),
        ),
    ]
