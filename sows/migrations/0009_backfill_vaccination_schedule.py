import re
from collections import defaultdict
from datetime import date

from django.db import migrations


DATE_AT_END = re.compile(r"(\d{4}-\d{2}-\d{2})$")


def _as_date(value):
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _scheduled_date(details, cycle_id, event_date):
    value = _as_date(details.get("scheduled_date"))
    if value:
        return value
    match = DATE_AT_END.search(cycle_id)
    if match:
        return _as_date(match.group(1))
    return event_date if cycle_id else None


def backfill_vaccination_schedule(apps, schema_editor):
    Plan = apps.get_model("sows", "VaccinationPlanModel")
    Event = apps.get_model("sows", "SowEventModel")
    Cycle = apps.get_model("sows", "VaccinationCycleModel")

    plans_by_farm_and_name = defaultdict(list)
    plans = list(Plan.objects.all())
    for plan in plans:
        plans_by_farm_and_name[(plan.farm_id, plan.name.casefold())].append(plan)

    matched_plan_ids = set()
    events_to_update = []
    cycles_to_create = []
    events = Event.objects.filter(event_type="VACCINATION").select_related("sow")

    for event in events.iterator(chunk_size=500):
        details = event.details if isinstance(event.details, dict) else {}
        vaccine_name = str(details.get("vaccine_name") or "")[:100]
        cycle_id = str(details.get("cycle_id") or "")[:160]
        matches = plans_by_farm_and_name.get((event.sow.farm_id, vaccine_name.casefold()), [])
        plan = matches[0] if len(matches) == 1 else None
        scheduled_date = _scheduled_date(details, cycle_id, event.event_date)

        event.vaccine_name = vaccine_name
        event.cycle_id = cycle_id
        event.scheduled_date = scheduled_date
        if plan:
            event.vaccination_plan_id = plan.id
            matched_plan_ids.add(plan.id)
        events_to_update.append(event)

        if plan and cycle_id and scheduled_date:
            cycles_to_create.append(Cycle(
                plan_id=plan.id,
                sow_id=event.sow_id,
                cycle_id=cycle_id,
                scheduled_date=scheduled_date,
                status="COMPLETED",
                completed_at=event.event_date,
            ))

    if events_to_update:
        Event.objects.bulk_update(
            events_to_update,
            ("vaccine_name", "cycle_id", "scheduled_date", "vaccination_plan"),
            batch_size=500,
        )
    Event.objects.filter(vaccine_name__isnull=True).update(vaccine_name="")
    Event.objects.filter(cycle_id__isnull=True).update(cycle_id="")
    if cycles_to_create:
        Cycle.objects.bulk_create(cycles_to_create, batch_size=500, ignore_conflicts=True)

    plans_to_update = []
    for plan in plans:
        if plan.interval_months is None:
            continue
        plan.interval_value = plan.interval_months
        plan.interval_unit = "MONTHS"
        plan.schedule_mode = "FROM_LAST_COMPLETED"
        plan.scope = "ALL"
        if plan.id not in matched_plan_ids:
            plan.is_active = False
            plan.requires_configuration = True
        plans_to_update.append(plan)

    if plans_to_update:
        Plan.objects.bulk_update(
            plans_to_update,
            (
                "interval_value",
                "interval_unit",
                "schedule_mode",
                "scope",
                "is_active",
                "requires_configuration",
            ),
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sows", "0008_vaccination_schedule_schema"),
    ]

    operations = [
        migrations.RunPython(backfill_vaccination_schedule, migrations.RunPython.noop),
    ]
