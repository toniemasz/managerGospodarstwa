# sows/views.py
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from datetime import date

from .application.services import SowDashboardService
from .infrastructure.repositories import SowRepository
from .forms import SowForm, SowEventForm, VaccinationPlanForm
from .models import SowModel, SowEventModel
from django.http import HttpResponse
import traceback
from django.utils import timezone


@login_required
def modules_home_view(request):
    return render(request, 'sows/modules_home.html')


@login_required
def dashboard_view(request):
    try:
        service = SowDashboardService()
        context = service.get_dashboard_summary()
        return render(request, 'sows/dashboard.html', context)
    except Exception as e:
        error_html = f"<h2>Wystąpił błąd w danych!</h2><br><b>Powód:</b> {str(e)}<br><br><b>Dokładne miejsce w kodzie:</b><br><pre>{traceback.format_exc()}</pre>"
        return HttpResponse(error_html, status=500)


@login_required
def add_sow_view(request):
    if request.method == 'POST':
        form = SowForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = SowForm()
    return render(request, 'sows/add_sow.html', {'form': form})


@login_required
def add_vaccination_plan_view(request):
    """Widok odpowiedzialny za konfigurację nowych szczepień cyklicznych."""
    if request.method == 'POST':
        form = VaccinationPlanForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
    else:
        form = VaccinationPlanForm()

    return render(request, 'sows/add_vaccination_plan.html', {'form': form})
@login_required
def sow_detail_view(request, sow_id):
    db_sow = get_object_or_404(SowModel, id=sow_id)

    if request.method == 'POST' and 'edit_sow' in request.POST:
        form = SowForm(request.POST, instance=db_sow)
        if form.is_valid():
            form.save()
            return redirect('sow_detail', sow_id=db_sow.id)
    else:
        form = SowForm(instance=db_sow)

    repo = SowRepository()
    sow = repo.get_sow_by_id(sow_id)

    return render(request, 'sows/sow_detail.html', {'sow': sow, 'form': form})


@login_required
def add_event_view(request, sow_id):
    db_sow = get_object_or_404(SowModel, id=sow_id)

    repo = SowRepository()
    domain_sow = repo.get_sow_by_id(sow_id)
    domain_sow.update_state_for_date(date.today())
    
    if request.method == 'POST':
        form = SowEventForm(request.POST, sow_status=domain_sow.status)
        if form.is_valid():
            event = form.save(commit=False)
            event.sow = db_sow
            event.save()
            return redirect('sow_detail', sow_id=sow_id)
    else:
        form = SowEventForm(sow_status=domain_sow.status)

    return render(request, 'sows/add_event.html', {'form': form, 'sow': db_sow})


@login_required
def bulk_pregnancy_check_view(request):
    """Zwraca ekran do masowego wprowadzania wyników badań USG i zapisuje je."""
    service = SowDashboardService()
    context = service.get_dashboard_summary()
    sows_to_check = context['sows_to_check_usg']

    if request.method == 'POST':
        for sow in sows_to_check:
            result = request.POST.get(f'result_{sow.id}')

            if result in ['TAK', 'NIE', '?']:
                db_sow = get_object_or_404(SowModel, id=sow.id)
                SowEventModel.objects.create(
                    sow=db_sow,
                    event_type='PREGNANCY_CHECK',
                    event_date=date.today(),
                    details={'result': result}
                )
        return redirect('dashboard')

    return render(request, 'sows/bulk_pregnancy.html', {'sows': sows_to_check})


@login_required
def bulk_vaccinate_view(request):
    """Odbiera żądanie z dashboardu, wyświetla ekran potwierdzenia i zapisuje zdarzenia."""
    if request.method == 'POST':
        sow_ids = request.POST.getlist('sow_ids')
        vaccine_name = request.POST.get('vaccine_name')
        cycle_id = request.POST.get('cycle_id')

        if request.POST.get('confirm') == 'yes':
            _create_vaccination_events(sow_ids, vaccine_name, cycle_id)
            return redirect('dashboard')
        else:
            sows = SowModel.objects.filter(id__in=sow_ids)
            return render(request, 'sows/bulk_vaccinate.html', {
                'sows': sows,
                'vaccine_name': vaccine_name,
                'cycle_id': cycle_id
            })

    return redirect('dashboard')


@login_required
def edit_event_view(request, event_id):
    db_event = get_object_or_404(SowEventModel, id=event_id)
    sow_id = db_event.sow.id

    if request.method == 'POST':
        form = SowEventForm(request.POST, instance=db_event)
        if form.is_valid():
            form.save()
            return redirect('sow_detail', sow_id=sow_id)
    else:
        initial_data = _get_event_initial_data(db_event)
        form = SowEventForm(instance=db_event, initial=initial_data)

    return render(request, 'sows/add_event.html', {
        'form': form,
        'event': db_event,
        'sow': db_event.sow
    })


@login_required
def delete_sow_view(request, sow_id):
    if request.method == 'POST':
        db_sow = get_object_or_404(SowModel, id=sow_id)

        if request.POST.get('archive') == 'on':
            db_sow.is_archived = True
            db_sow.archived_at = timezone.now()
            db_sow.save()
        else:
            db_sow.delete()

        return redirect('dashboard')
    return redirect('sow_detail', sow_id=sow_id)

@login_required
def archived_sows_view(request):
    try:
        service = SowDashboardService()
        archived_sows = service.get_archived_sows_list()
        return render(request, 'sows/archived_sows.html', {'archived_sows': archived_sows})
    except Exception as e:
        import traceback
        error_html = f"<h2>Wystąpił błąd!</h2><br><b>Powód:</b> {str(e)}<br><pre>{traceback.format_exc()}</pre>"
        return HttpResponse(error_html, status=500)

@login_required
def delete_event_view(request, event_id):
    if request.method == 'POST':
        db_event = get_object_or_404(SowEventModel, id=event_id)
        sow_id = db_event.sow.id
        db_event.delete()
        return redirect('sow_detail', sow_id=sow_id)
    return redirect('dashboard')


# Helper functions
def _create_vaccination_events(sow_ids: list, vaccine_name: str, cycle_id: str) -> None:
    """Tworzy zdarzenia szczepienia dla wskazanych macior."""
    for s_id in sow_ids:
        db_sow = get_object_or_404(SowModel, id=s_id)
        SowEventModel.objects.create(
            sow=db_sow,
            event_type='VACCINATION',
            event_date=date.today(),
            details={
                'vaccine_name': vaccine_name,
                'cycle_id': cycle_id
            }
        )


def _get_event_initial_data(db_event: SowEventModel) -> dict:
    """Przygotowuje dane początkowe formularza na podstawie typu zdarzenia."""
    event_details_mapping = {
        'INSEMINATION': {'technician': db_event.details.get('technician', '')},
        'PREGNANCY_CHECK': {'pregnancy_result': db_event.details.get('result', '')},
        'FARROWING': {
            'born_alive': db_event.details.get('born_alive', 0),
            'born_dead': db_event.details.get('born_dead', 0)
        },
        'WEANING': {'count': db_event.details.get('count', 0)},
        'VACCINATION': {'vaccine_name': db_event.details.get('vaccine_name', '')},
    }
    return event_details_mapping.get(db_event.event_type, {})
