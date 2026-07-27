from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sows", "0013_normalized_business_identifiers"),
    ]

    operations = [
        migrations.AlterField(
            model_name="soweventmodel",
            name="vaccination_plan",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vaccination_events",
                to="sows.vaccinationplanmodel",
                verbose_name="Plan szczepień",
            ),
        ),
        migrations.AlterField(
            model_name="vaccinationcyclemodel",
            name="plan",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cycle_records",
                to="sows.vaccinationplanmodel",
                verbose_name="Plan szczepień",
            ),
        ),
    ]
