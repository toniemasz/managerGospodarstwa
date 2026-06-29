from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def assign_missing_farms(apps, schema_editor):
    Farm = apps.get_model("farms", "FarmModel")
    Sow = apps.get_model("sows", "SowModel")
    Plan = apps.get_model("sows", "VaccinationPlanModel")
    if not Sow.objects.filter(farm__isnull=True).exists() and not Plan.objects.filter(farm__isnull=True).exists():
        return
    farm = Farm.objects.order_by("owner_id", "id").first()
    if farm is None:
        app_label, model_name = settings.AUTH_USER_MODEL.split(".")
        User = apps.get_model(app_label, model_name)
        user = User.objects.order_by("id").first()
        if user is None:
            user = User.objects.create(username="gospodarstwo", password="!")
        farm = Farm.objects.create(owner_id=user.pk, name="Gospodarstwo")
    Sow.objects.filter(farm__isnull=True).update(farm=farm)
    for plan in Plan.objects.filter(farm__isnull=True).order_by("id"):
        if Plan.objects.filter(farm=farm, name=plan.name).exists():
            suffix = f" (legacy {plan.pk})"
            plan.name = f"{plan.name[:100 - len(suffix)]}{suffix}"
        plan.farm = farm
        plan.save(update_fields=["farm", "name"])


class Migration(migrations.Migration):
    dependencies = [("farms", "0005_auditlogmodel"), ("sows", "0005_farm_scope")]
    operations = [
        migrations.RunPython(assign_missing_farms, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="sowmodel",
            name="farm",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sows", to="farms.farmmodel", verbose_name="Gospodarstwo"),
        ),
        migrations.AlterField(
            model_name="vaccinationplanmodel",
            name="farm",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vaccination_plans", to="farms.farmmodel", verbose_name="Gospodarstwo"),
        ),
    ]
