from django.db import migrations


def show_statistics_module(apps, schema_editor):
    FarmSettingsModel = apps.get_model("farms", "FarmSettingsModel")
    old_default_nav = ["tasks", "sows", "feed", "sales"]
    for settings in FarmSettingsModel.objects.all():
        visible_modules = list(settings.visible_modules or [])
        nav_modules = list(settings.nav_modules or [])
        changed = False
        if "statistics" not in visible_modules:
            visible_modules.append("statistics")
            settings.visible_modules = visible_modules
            changed = True
        if nav_modules == old_default_nav and "statistics" not in nav_modules:
            nav_modules.insert(1, "statistics")
            settings.nav_modules = nav_modules
            changed = True
        if changed:
            settings.save(update_fields=["visible_modules", "nav_modules", "updated_at"])


def hide_statistics_module(apps, schema_editor):
    FarmSettingsModel = apps.get_model("farms", "FarmSettingsModel")
    for settings in FarmSettingsModel.objects.all():
        settings.visible_modules = [key for key in list(settings.visible_modules or []) if key != "statistics"]
        settings.nav_modules = [key for key in list(settings.nav_modules or []) if key != "statistics"]
        settings.save(update_fields=["visible_modules", "nav_modules", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("farms", "0010_font_scale_range"),
    ]

    operations = [
        migrations.RunPython(show_statistics_module, hide_statistics_module),
    ]
