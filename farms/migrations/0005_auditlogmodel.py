from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("farms", "0004_remove_legacy_low_stock_threshold"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditLogModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=50)),
                ("model_label", models.CharField(max_length=100)),
                ("object_id", models.CharField(blank=True, max_length=100)),
                ("object_repr", models.CharField(blank=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="audit_logs", to="farms.farmmodel")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="farm_audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Wpis historii zmian",
                "verbose_name_plural": "Historia zmian",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.AddIndex(
            model_name="auditlogmodel",
            index=models.Index(fields=["farm", "-created_at"], name="audit_farm_created_idx"),
        ),
    ]
