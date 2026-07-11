import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("farms", "0012_feed_serving_mode")]
    operations = [
        migrations.CreateModel(
            name="BackupImportPreviewModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("FARM", "Gospodarstwo"), ("DATABASE", "Cała baza")], max_length=16)),
                ("payload", models.BinaryField()),
                ("sha256", models.CharField(max_length=64)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("farm", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="backup_import_previews", to="farms.farmmodel")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="backup_import_previews", to=settings.AUTH_USER_MODEL)),
            ],
        )
    ]
