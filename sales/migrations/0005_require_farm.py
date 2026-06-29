from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_missing_farms(apps, schema_editor):
    Farm = apps.get_model("farms", "FarmModel")
    Sale = apps.get_model("sales", "PigSaleModel")
    if not Sale.objects.filter(farm__isnull=True).exists():
        return
    farm = Farm.objects.order_by("owner_id", "id").first()
    if farm is None:
        app_label, model_name = settings.AUTH_USER_MODEL.split(".")
        User = apps.get_model(app_label, model_name)
        user = User.objects.order_by("id").first()
        if user is None:
            user = User.objects.create(username="gospodarstwo", password="!")
        farm = Farm.objects.create(owner_id=user.pk, name="Gospodarstwo")
    Sale.objects.filter(farm__isnull=True).update(farm=farm)


class Migration(migrations.Migration):
    dependencies = [("farms", "0005_auditlogmodel"), ("sales", "0004_remove_pigsalemodel_slaughter_date_and_more")]
    operations = [
        migrations.RunPython(assign_missing_farms, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pigsalemodel",
            name="farm",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="pig_sales", to="farms.farmmodel", verbose_name="Gospodarstwo"),
        ),
    ]
