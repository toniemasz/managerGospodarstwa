# sows/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from datetime import date

from .application.services import SowDashboardService
from .infrastructure.repositories import SowRepository
from .forms import SowForm, SowEventForm
from .models import SowModel, SowEventModel


@login_required
def modules_home_view(request):
    return render(request, 'sows/modules_home.html')


@login_required
def dashboard_view(request):
    service = SowDashboardService()
    context = service.get_dashboard_summary()
    return render(request, 'sows/dashboard.html', context)


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
def bulk_vaccinate_view(request):
    """Rejestruje zdarzenie szczepienia ochronnego dla całej zaznaczonej grupy macior."""
    if request.method == 'POST':
        sow_ids = request.POST.getlist('sow_ids')
        vaccine_name = request.POST.get('vaccine_name')
        cycle_id = request.POST.get('cycle_id')

        if sow_ids and vaccine_name:
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
        initial_data = {}
        if db_event.event_type == 'INSEMINATION':
            initial_data['technician'] = db_event.details.get('technician', '')
        elif db_event.event_type == 'PREGNANCY_CHECK':
            initial_data['pregnancy_result'] = db_event.details.get('result', '')
        elif db_event.event_type == 'FARROWING':
            initial_data['born_alive'] = db_event.details.get('born_alive', 0)
            initial_data['born_dead'] = db_event.details.get('born_dead', 0)
        elif db_event.event_type == 'WEANING':
            initial_data['count'] = db_event.details.get('count', 0)
        elif db_event.event_type == 'VACCINATION':
            initial_data['vaccine_name'] = db_event.details.get('vaccine_name', '')

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
        db_sow.delete()
        return redirect('dashboard')
    return redirect('sow_detail', sow_id=sow_id)


@login_required
def delete_event_view(request, event_id):
    if request.method == 'POST':
        db_event = get_object_or_404(SowEventModel, id=event_id)
        sow_id = db_event.sow.id
        db_event.delete()
        return redirect('sow_detail', sow_id=sow_id)
    return redirect('dashboard')