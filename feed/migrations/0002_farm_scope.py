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


def assign_existing_feed_data(apps, schema_editor):
    IngredientModel = apps.get_model('feed', 'IngredientModel')
    RecipeModel = apps.get_model('feed', 'RecipeModel')

    has_legacy_data = (
        IngredientModel.objects.filter(farm__isnull=True).exists()
        or RecipeModel.objects.filter(farm__isnull=True).exists()
    )
    if not has_legacy_data:
        return

    farm = _ensure_user_farms(apps)
    IngredientModel.objects.filter(farm__isnull=True).update(farm=farm)
    RecipeModel.objects.filter(farm__isnull=True).update(farm=farm)


class Migration(migrations.Migration):

    dependencies = [
        ('farms', '0001_initial'),
        ('feed', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='ingredientmodel',
            name='farm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ingredients', to='farms.farmmodel', verbose_name='Gospodarstwo'),
        ),
        migrations.AddField(
            model_name='recipemodel',
            name='farm',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='recipes', to='farms.farmmodel', verbose_name='Gospodarstwo'),
        ),
        migrations.RunPython(assign_existing_feed_data, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='ingredientmodel',
            name='name',
            field=models.CharField(max_length=100, verbose_name='Nazwa składnika'),
        ),
        migrations.AlterField(
            model_name='recipemodel',
            name='name',
            field=models.CharField(max_length=150, verbose_name='Nazwa receptury'),
        ),
        migrations.AddConstraint(
            model_name='ingredientmodel',
            constraint=models.UniqueConstraint(fields=('farm', 'name'), name='unique_ingredient_name_per_farm'),
        ),
        migrations.AddConstraint(
            model_name='recipemodel',
            constraint=models.UniqueConstraint(fields=('farm', 'name'), name='unique_recipe_name_per_farm'),
        ),
    ]
