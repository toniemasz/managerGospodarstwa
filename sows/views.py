# sows/views.py
import logging
import traceback
from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from .application.services import SowDashboardService, SowManagementService
from .infrastructure.repositories import SowRepository
from .forms import SowForm, SowEventForm, VaccinationPlanForm
from .models import SowModel, SowEventModel


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
            SowManagementService.create_sow(form.cleaned_data)
            return redirect('dashboard')
    else:
        form = SowForm()
    return render(request, 'sows/add_sow.html', {'form': form})


@login_required
def add_vaccination_plan_view(request):
    if request.method == 'POST':
        form = VaccinationPlanForm(request.POST)
        if form.is_valid():
            SowManagementService.create_vaccination_plan(form.cleaned_data)
            return redirect('dashboard')
    else:
        form = VaccinationPlanForm()

    return render(request, 'sows/add_vaccination_plan.html', {'form': form})


@login_required
def sow_detail_view(request, sow_id):
    db_sow = get_object_or_404(SowModel, id=sow_id)
    repo = SowRepository()
    sow = repo.get_sow_by_id(sow_id)

    if request.method == 'POST' and 'edit_sow' in request.POST:
        # Przekazujemy instancję do formularza, aby zwalidował pola unikalne itp.,
        # ale fizyczny zapis przekazujemy do serwisu.
        form = SowForm(request.POST, instance=db_sow)
        if form.is_valid():
            SowManagementService.update_sow(sow_id, form.cleaned_data)
            return redirect('sow_detail', sow_id=sow_id)
    else:
        form = SowForm(instance=db_sow)

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
            SowManagementService.create_sow_event(sow_id, form.cleaned_data)
            return redirect('sow_detail', sow_id=sow_id)
    else:
        form = SowEventForm(sow_status=domain_sow.status)

    return render(request, 'sows/add_event.html', {'form': form, 'sow': db_sow})


@login_required
def bulk_pregnancy_check_view(request):
    service = SowDashboardService()
    context = service.get_dashboard_summary()
    sows_to_check = context['sows_to_check_usg']

    if request.method == 'POST':
        check_results = {}
        for sow in sows_to_check:
            result = request.POST.get(f'result_{sow.id}')
            if result:
                check_results[sow.id] = result

        SowManagementService.bulk_pregnancy_check(check_results)
        return redirect('dashboard')

    return render(request, 'sows/bulk_pregnancy.html', {'sows': sows_to_check})


@login_required
def bulk_vaccinate_view(request):
    if request.method == 'POST':
        sow_ids = request.POST.getlist('sow_ids')
        vaccine_name = request.POST.get('vaccine_name')
        cycle_id = request.POST.get('cycle_id')

        if request.POST.get('confirm') == 'yes':
            SowManagementService.bulk_vaccinate(sow_ids, vaccine_name, cycle_id)
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
            SowManagementService.update_sow_event(event_id, form.cleaned_data)
            return redirect('sow_detail', sow_id=sow_id)
    else:
        initial_data = SowManagementService.get_event_initial_data(db_event)
        form = SowEventForm(instance=db_event, initial=initial_data)

    return render(request, 'sows/add_event.html', {
        'form': form,
        'event': db_event,
        'sow': db_event.sow
    })


@login_required
def delete_sow_view(request, sow_id):
    if request.method == 'POST':
        is_archived = request.POST.get('archive') == 'on'
        SowManagementService.delete_or_archive_sow(sow_id, is_archived)
        return redirect('dashboard')
    return redirect('sow_detail', sow_id=sow_id)


@login_required
def archived_sows_view(request):
    try:
        service = SowDashboardService()
        archived_sows = service.get_archived_sows_list()
        return render(request, 'sows/archived_sows.html', {'archived_sows': archived_sows})
    except Exception as e:
        error_html = f"<h2>Wystąpił błąd!</h2><br><b>Powód:</b> {str(e)}<br><pre>{traceback.format_exc()}</pre>"
        return HttpResponse(error_html, status=500)


@login_required
def general_statistics_view(request):
    try:
        metric_key = request.GET.get('metric', 'born_alive')
        order = request.GET.get('order', 'desc')

        try:
            months = int(request.GET.get('months', '6'))
        except ValueError:
            months = 6

        service = SowDashboardService()
        context = service.get_general_statistics(metric_key=metric_key, months_limit=months, order=order)
        return render(request, 'sows/analytics.html', context)
    except Exception as e:
        error_html = f"<h2>Błąd podczas generowania statystyk</h2><pre>{traceback.format_exc()}</pre>"
        return HttpResponse(error_html, status=500)


@login_required
def delete_event_view(request, event_id):
    if request.method == 'POST':
        sow_id = SowManagementService.delete_sow_event(event_id)
        return redirect('sow_detail', sow_id=sow_id)
    return redirect('dashboard')
