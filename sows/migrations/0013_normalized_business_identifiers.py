import django.db.models.functions.text
from django.db import migrations, models


def _next_unique_value(value, used, max_length):
    base = value.strip()
    candidate = base
    suffix_number = 0
    while candidate.lower() in used:
        suffix_number += 1
        suffix = f" ({suffix_number})"
        candidate = f"{base[:max_length - len(suffix)].rstrip()}{suffix}"
    used.add(candidate.lower())
    return candidate


def normalize_sow_and_plan_identifiers(apps, schema_editor):
    Sow = apps.get_model('sows', 'SowModel')
    Plan = apps.get_model('sows', 'VaccinationPlanModel')

    used_active_tags = {}
    for sow in Sow.objects.order_by('farm_id', 'id').iterator():
        cleaned = sow.ear_tag.strip()
        if sow.is_archived:
            candidate = cleaned
        else:
            used = used_active_tags.setdefault(sow.farm_id, set())
            candidate = _next_unique_value(cleaned, used, 50)
        if candidate != sow.ear_tag:
            Sow.objects.filter(pk=sow.pk).update(ear_tag=candidate)

    used_plan_names = {}
    for plan in Plan.objects.order_by('farm_id', 'id').iterator():
        used = used_plan_names.setdefault(plan.farm_id, set())
        candidate = _next_unique_value(plan.name, used, 100)
        if candidate != plan.name:
            Plan.objects.filter(pk=plan.pk).update(name=candidate)


class Migration(migrations.Migration):
    dependencies = [
        ('farms', '0014_default_automatic_feed_serving'),
        ('sows', '0012_piglettransfermodel_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='vaccinationplanmodel',
            name='unique_vaccination_plan_name_per_farm',
        ),
        migrations.RunPython(normalize_sow_and_plan_identifiers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='sowmodel',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('ear_tag')
                ),
                models.F('farm'),
                condition=models.Q(('is_archived', False)),
                name='unique_active_sow_ear_tag_per_farm_ci',
            ),
        ),
        migrations.AddConstraint(
            model_name='vaccinationplanmodel',
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('name')
                ),
                models.F('farm'),
                name='unique_vacc_plan_name_per_farm_ci',
            ),
        ),
    ]
