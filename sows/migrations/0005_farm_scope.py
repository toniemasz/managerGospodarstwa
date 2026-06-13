from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def _user_model_label() -> tuple[str, str]:
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    return app_label, model_name


def _ensure_user_farms(apps):
    app_label, model_name = _user_model_label()
    UserModel = apps.get_model(app_label, model_name)
    FarmModel = apps.get_model('farms', 'FarmModel')

    legacy_user, created = UserModel.objects.get_or_create(
        username='gospodarstwo',
        defaults={
            'first_name': 'Dane',
            'last_name': 'historyczne',
            'password': '!',
        },
    )
    if created and hasattr(legacy_user, 'set_unusable_password'):
        legacy_user.set_unusable_password()
        legacy_user.save(update_fields=['password'])

    users = list(UserModel.objects.order_by('id'))
    for user in users:
        if user.pk == legacy_user.pk:
            continue
        username = getattr(user, 'username', '') or getattr(user, 'email', '') or str(user.pk)
        FarmModel.objects.get_or_create(
            owner_id=user.pk,
            defaults={'name': f'Gospodarstwo {username}'},
        )

    farm, _ = FarmModel.objects.get_or_create(
        owner_id=legacy_user.pk,
        defaults={'name': 'Gospodarstwo'},
    )
    return farm


def assign_existing_sow_data(apps, schema_editor):
    SowModel = apps.get_model('sows', 'SowModel')
    VaccinationPlanModel = apps.get_model('sows', 'VaccinationPlanModel')

    has_legacy_data = (
        SowModel.objects.filter(farm__isnull=True).exists()
        or VaccinationPlanModel.objects.filter(farm__isnull=True).exists()
    )
    if not has_legacy_data:
        return

    farm = _ensure_user_farms(apps)
    SowModel.objects.filter(farm__isnull=True).update(farm=farm)
    VaccinationPlanModel.objects.filter(farm__isnull=True).update(farm=farm)


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0001_initial'),
        ('sows', '0004_sowmodel_archive_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='sowmodel',
            name='farm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sows', to='farms.farmmodel', verbose_name='Gospodarstwo'),
        ),
        migrations.AddField(
            model_name='vaccinationplanmodel',
            name='farm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='vaccination_plans', to='farms.farmmodel', verbose_name='Gospodarstwo'),
        ),
        migrations.RunPython(assign_existing_sow_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='vaccinationplanmodel',
            name='name',
            field=models.CharField(max_length=100, verbose_name='Nazwa szczepienia'),
        ),
        migrations.AddConstraint(
            model_name='vaccinationplanmodel',
            constraint=models.UniqueConstraint(fields=('farm', 'name'), name='unique_vaccination_plan_name_per_farm'),
        ),
    ]
