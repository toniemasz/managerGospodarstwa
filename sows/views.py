from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from datetime import date
from .models import SowModel
from .domain.entities import Sow, SowEvent


@login_required
def modules_home_view(request):
    return render(request, 'sows/modules_home.html')


@login_required
def dashboard_view(request):
    today = date.today()
    db_sows = SowModel.objects.prefetch_related('events').all()

    sows_entities = []
    sows_to_vaccinate = []

    total_active_sows = len(db_sows)
    inseminated_count = 0
    lactating_count = 0
    idle_count = 0

    for db_sow in db_sows:
        sow = Sow(
            sow_id=db_sow.sow_id,
            ear_tag=db_sow.ear_tag,
            birth_date=db_sow.birth_date
        )

        events = [
            SowEvent(event_type=e.event_type, event_date=e.event_date, details=e.details)
            for e in db_sow.events.all()
        ]
        sow.load_history(events)
        sows_entities.append(sow)

        if sow.status == "INSEMINATED":
            inseminated_count += 1
        elif sow.status == "LACTATING":
            lactating_count += 1
        elif sow.status == "IDLE":
            idle_count += 1

        if sow.needs_vaccination(current_date=today):
            sows_to_vaccinate.append(sow)

    context = {
        'total_sows': total_active_sows,
        'inseminated_count': inseminated_count,
        'lactating_count': lactating_count,
        'idle_count': idle_count,
        'sows_to_vaccinate': sows_to_vaccinate,
        'all_sows': sows_entities,
    }
    return render(request, 'sows/dashboard.html', context)
