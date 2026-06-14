import logging
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages

from .services.sow_dashboard_service import SowDashboardService
from .services.sow_repository import SowRepository
from .services.bulk_event_service import BulkSowEventService
from .forms import (
    BulkSowEventFormSet,
    SowForm,
    SowEventForm,
    VaccinationPlanForm,
    empty_bulk_event_initials,
)
from .models import SowModel, SowEventModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.date_range import PERIOD_OPTIONS, parse_date_range

logger = logging.getLogger(__name__)


def _current_farm(request):
    farm = getattr(request, 'farm', None)
    if farm is None and request.user.is_authenticated:
        farm = get_or_create_user_farm(request.user)
        request.farm = farm
    return farm


@login_required
def modules_home_view(request):
    return render(request, 'sows/modules_home.html')


@login_required
def dashboard_view(request):
    try:
        service = SowDashboardService(farm=_current_farm(request))
        context = service.get_dashboard_summary()
        return render(request, 'sows/dashboard.html', context)
    except Exception:
        logger.exception("Błąd w panelu macior")
        return HttpResponse("Wystąpił błąd w danych. Szczegóły zapisano w logach aplikacji.", status=500)


@login_required
def add_sow_view(request):
    farm = _current_farm(request)
    if request.method == 'POST':
        form = SowForm(request.POST)
        if form.is_valid():
            sow = form.save(commit=False)
            sow.farm = farm
            sow.save()
            return redirect('dashboard')
    else:
        form = SowForm()
    return render(request, 'sows/add_sow.html', {'form': form})


@login_required
def add_vaccination_plan_view(request):
    """Widok odpowiedzialny za konfigurację nowych szczepień cyklicznych."""
    farm = _current_farm(request)
    if request.method == 'POST':
        form = VaccinationPlanForm(request.POST, farm=farm)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.farm = farm
            plan.save()
            return redirect('dashboard')
    else:
        form = VaccinationPlanForm(farm=farm)

    return render(request, 'sows/add_vaccination_plan.html', {'form': form})


@login_required
def sow_detail_view(request, sow_id):
    farm = _current_farm(request)
    db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

    if request.method == 'POST' and 'edit_sow' in request.POST:
        form = SowForm(request.POST, instance=db_sow)
        if form.is_valid():
            form.save()
            return redirect('sow_detail', sow_id=db_sow.id)
    else:
        form = SowForm(instance=db_sow)

    repo = SowRepository(farm=farm)
    sow = repo.get_sow_by_id(sow_id)

    return render(request, 'sows/sow_detail.html', {'sow': sow, 'form': form})


@login_required
def add_event_view(request, sow_id):
    farm = _current_farm(request)
    db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

    repo = SowRepository(farm=farm)
    sow = repo.get_sow_by_id(sow_id)
    sow.update_state_for_date(date.today())

    if request.method == 'POST':
        form = SowEventForm(request.POST, sow_status=sow.status, farm=farm)
        if form.is_valid():
            event = form.save(commit=False)
            event.sow = db_sow
            event.save()
            return redirect('sow_detail', sow_id=sow_id)
    else:
        form = SowEventForm(sow_status=sow.status, farm=farm, initial={'event_date': date.today()})

    return render(request, 'sows/add_event.html', {'form': form, 'sow': db_sow})


@login_required
def bulk_sow_events_view(request):
    farm = _current_farm(request)
    service = BulkSowEventService(farm=farm)
    sows = SowModel.objects.filter(farm=farm, is_archived=False).order_by('ear_tag')
    is_single = request.GET.get('rows') == '1'

    try:
        requested_rows = int(request.GET.get('rows', '1' if is_single else '8'))
    except ValueError:
        requested_rows = 1 if is_single else 8

    if is_single:
        initial_count = 1
    else:
        initial_count = max(2, min(20, requested_rows))

    if request.method == 'POST':
        formset = BulkSowEventFormSet(request.POST, prefix='events', form_kwargs={'farm': farm})
        if formset.is_valid():
            rows = service.build_rows_from_formset(formset)
            if not rows:
                formset.non_form_errors()
                messages.error(request, "Dodaj przynajmniej jeden wiersz zdarzenia.")
            else:
                validation = service.validate_rows(rows)
                if validation.is_valid:
                    created_count = service.create_events(rows)
                    messages.success(request, f"Zapisano {created_count} zdarzeń.")
                    return redirect('dashboard')

                for form_index, row_errors in validation.errors.items():
                    for error in row_errors:
                        formset.forms[form_index].add_error(None, error)
                messages.error(request, "Nie zapisano zdarzeń. Popraw oznaczone wiersze.")
    else:
        formset = BulkSowEventFormSet(
            prefix='events',
            initial=empty_bulk_event_initials(initial_count),
            form_kwargs={'farm': farm},
        )

    return render(request, 'sows/bulk_events.html', {
        'formset': formset,
        'sows': sows,
        'is_single': is_single,
    })


@login_required
def bulk_pregnancy_check_view(request):
    """Zwraca ekran do masowego wprowadzania wyników badań USG i zapisuje je."""
    farm = _current_farm(request)
    service = SowDashboardService(farm=farm)
    context = service.get_dashboard_summary()
    sows_to_check = context['sows_to_check_usg']

    if request.method == 'POST':
        for sow in sows_to_check:
            result = request.POST.get(f'result_{sow.id}')

            if result in ['TAK', 'NIE', '?']:
                db_sow = get_object_or_404(SowModel, id=sow.id, farm=farm)
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
    farm = _current_farm(request)
    if request.method == 'POST':
        sow_ids = request.POST.getlist('sow_ids')
        vaccine_name = request.POST.get('vaccine_name')
        cycle_id = request.POST.get('cycle_id')

        if request.POST.get('confirm') == 'yes':
            _create_vaccination_events(sow_ids, vaccine_name, cycle_id, farm)
            return redirect('dashboard')
        else:
            sows = SowModel.objects.filter(id__in=sow_ids, farm=farm)
            return render(request, 'sows/bulk_vaccinate.html', {
                'sows': sows,
                'vaccine_name': vaccine_name,
                'cycle_id': cycle_id
            })

    return redirect('dashboard')


@login_required
def edit_event_view(request, event_id):
    farm = _current_farm(request)
    db_event = get_object_or_404(SowEventModel, id=event_id, sow__farm=farm)
    sow_id = db_event.sow.id

    if request.method == 'POST':
        form = SowEventForm(request.POST, instance=db_event, farm=farm)
        if form.is_valid():
            form.save()
            return redirect('sow_detail', sow_id=sow_id)
    else:
        initial_data = _get_event_initial_data(db_event)
        form = SowEventForm(instance=db_event, initial=initial_data, farm=farm)

    return render(request, 'sows/add_event.html', {
        'form': form,
        'event': db_event,
        'sow': db_event.sow
    })


@login_required
def delete_sow_view(request, sow_id):
    farm = _current_farm(request)
    if request.method == 'POST':
        db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

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
        service = SowDashboardService(farm=_current_farm(request))
        archived_sows = service.get_archived_sows_list()
        return render(request, 'sows/archived_sows.html', {'archived_sows': archived_sows})
    except Exception:
        logger.exception("Błąd w archiwum macior")
        return HttpResponse("Wystąpił błąd w archiwum. Szczegóły zapisano w logach aplikacji.", status=500)


@login_required
def general_statistics_view(request):
    try:
        metric_key = request.GET.get('metric', 'born_alive')
        order = request.GET.get('order', 'desc')
        date_range = parse_date_range(request.GET, default_period='6m')

        months_by_period = {'3m': 3, '6m': 6, '12m': 12, 'all': 0}
        months = months_by_period.get(date_range.period, 6)

        service = SowDashboardService(farm=_current_farm(request))
        context = service.get_general_statistics(
            metric_key=metric_key,
            months_limit=months,
            order=order,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )
        context['date_filter'] = date_range
        context['period_options'] = PERIOD_OPTIONS
        return render(request, 'sows/analytics.html', context)
    except Exception:
        logger.exception("Błąd podczas generowania statystyk")
        return HttpResponse("Błąd podczas generowania statystyk. Szczegóły zapisano w logach aplikacji.", status=500)


@login_required
def delete_event_view(request, event_id):
    if request.method == 'POST':
        farm = _current_farm(request)
        db_event = get_object_or_404(SowEventModel, id=event_id, sow__farm=farm)
        sow_id = db_event.sow.id
        db_event.delete()
        return redirect('sow_detail', sow_id=sow_id)
    return redirect('dashboard')


def _create_vaccination_events(sow_ids: list, vaccine_name: str, cycle_id: str, farm) -> None:
    """Tworzy zdarzenia szczepienia dla wskazanych macior."""
    for s_id in sow_ids:
        db_sow = get_object_or_404(SowModel, id=s_id, farm=farm)
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
