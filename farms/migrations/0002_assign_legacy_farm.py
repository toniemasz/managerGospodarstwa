from django.conf import settings
from django.db import migrations


def _user_model_label() -> tuple[str, str]:
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    return app_label, model_name


def _get_or_create_legacy_farm(apps):
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

    farm, _ = FarmModel.objects.get_or_create(
        owner_id=legacy_user.pk,
        defaults={'name': 'Gospodarstwo'},
    )
    return farm


def assign_null_farm_records(apps, schema_editor):
    models_to_fix = [
        apps.get_model('sows', 'SowModel'),
        apps.get_model('sows', 'VaccinationPlanModel'),
        apps.get_model('feed', 'IngredientModel'),
        apps.get_model('feed', 'RecipeModel'),
        apps.get_model('sales', 'PigSaleModel'),
    ]

    if any(model.objects.filter(farm__isnull=True).exists() for model in models_to_fix):
        farm = _get_or_create_legacy_farm(apps)
        for model in models_to_fix:
            model.objects.filter(farm__isnull=True).update(farm=farm)
        return

    source_farm = _get_single_non_legacy_farm_with_records(apps, models_to_fix)
    if source_farm is None:
        return

    farm = _get_or_create_legacy_farm(apps)
    for model in models_to_fix:
        model.objects.filter(farm=source_farm).update(farm=farm)


def _get_single_non_legacy_farm_with_records(apps, models_to_fix):
    app_label, model_name = _user_model_label()
    UserModel = apps.get_model(app_label, model_name)
    FarmModel = apps.get_model('farms', 'FarmModel')

    if UserModel.objects.filter(username='gospodarstwo').exists():
        return None

    farms = list(FarmModel.objects.order_by('id'))
    if len(farms) != 1:
        return None

    farm = farms[0]
    owner = UserModel.objects.filter(pk=farm.owner_id).first()
    if owner is None or getattr(owner, 'username', '') == 'gospodarstwo':
        return None

    has_records = any(model.objects.filter(farm=farm).exists() for model in models_to_fix)
    return farm if has_records else None


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0001_initial'),
        ('sows', '0005_farm_scope'),
        ('feed', '0002_farm_scope'),
        ('sales', '0002_farm_scope'),
    ]

    operations = [
        migrations.RunPython(assign_null_farm_records, migrations.RunPython.noop),
    ]
