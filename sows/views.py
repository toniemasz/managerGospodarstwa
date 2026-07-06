import logging
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.core.exceptions import ValidationError

from .services.sow_dashboard_service import SowDashboardService
from .services.sow_repository import SowRepository, VaccinationPlanRepository
from .services.bulk_event_service import BulkSowEventService
from .services.sow_event_service import (
    FARROWING_DECISION_CANCEL,
    SowEventService,
)
from .forms import (
    BulkSowEventFormSet,
    SowForm,
    SowEventForm,
    VaccinationPlanForm,
    empty_bulk_event_initials,
)
from .models import SowModel, SowEventModel
from core.date_range import PERIOD_OPTIONS, parse_date_range
from core.filter_ui import filter_ui_state
from farms.services.current_farm import get_current_farm
from farms.services.farm_dashboard import FarmDashboardService
from farms.services.module_navigation import ModuleNavigationService
from farms.services.audit_log_service import log_action
from sows.domain.event_details import initial_data_from_event_details

logger = logging.getLogger(__name__)

@login_required
def modules_home_view(request):
    context = FarmDashboardService(get_current_farm(request)).get_context()
    return render(request, 'sows/modules_home.html', context)


@login_required
def modules_catalog_view(request):
    farm = get_current_farm(request)
    service = ModuleNavigationService(farm, request.resolver_match.url_name)
    modules = service.all_modules()
    return render(request, 'sows/modules_catalog.html', {
        'module_groups': service.grouped_modules(modules, include_settings=True),
    })


@login_required
def dashboard_view(request):
    try:
        service = SowDashboardService(farm=get_current_farm(request))
        context = service.get_dashboard_summary()
        return render(request, 'sows/dashboard.html', context)
    except Exception:
        logger.exception("Błąd w panelu macior")
        return HttpResponse("Wystąpił błąd w danych. Szczegóły zapisano w logach aplikacji.", status=500)


@login_required
def add_sow_view(request):
    farm = get_current_farm(request)
    if request.method == 'POST':
        form = SowForm(request.POST)
        if form.is_valid():
            sow = form.save(commit=False)
            sow.farm = farm
            sow.save()
            log_action(farm=farm, user=request.user, action="CREATE", obj=sow)
            return redirect('dashboard')
    else:
        form = SowForm()
    return render(request, 'sows/add_sow.html', {'form': form})


@login_required
def edit_sow_view(request, sow_id):
    farm = get_current_farm(request)
    db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

    if request.method == 'POST':
        form = SowForm(request.POST, instance=db_sow)
        if form.is_valid():
            sow = form.save()
            log_action(farm=farm, user=request.user, action="UPDATE", obj=sow)
            messages.success(request, "Dane maciory zostały zaktualizowane.")
            return redirect('sow_detail', sow_id=db_sow.id)
    else:
        form = SowForm(instance=db_sow)

    return render(request, 'sows/add_sow.html', {
        'form': form,
        'sow': db_sow,
        'is_edit': True,
    })


@login_required
def vaccination_plans_view(request):
    farm = get_current_farm(request)
    plans = VaccinationPlanRepository(farm=farm).get_all_plans()
    return render(request, 'sows/vaccination_plans.html', {'plans': plans})


@login_required
def add_vaccination_plan_view(request):
    """Widok odpowiedzialny za konfigurację nowych szczepień cyklicznych."""
    farm = get_current_farm(request)
    if request.method == 'POST':
        form = VaccinationPlanForm(request.POST, farm=farm)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.farm = farm
            plan.save()
            messages.success(request, "Reguła szczepienia została dodana.")
            return redirect('vaccination_plans')
    else:
        form = VaccinationPlanForm(farm=farm)

    return render(request, 'sows/add_vaccination_plan.html', {'form': form, 'is_edit': False})


@login_required
def edit_vaccination_plan_view(request, plan_id):
    farm = get_current_farm(request)
    plan = VaccinationPlanRepository(farm=farm).get_plan_model_by_id(plan_id)

    if request.method == 'POST':
        form = VaccinationPlanForm(request.POST, instance=plan, farm=farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Reguła szczepienia została zaktualizowana.")
            return redirect('vaccination_plans')
    else:
        form = VaccinationPlanForm(instance=plan, farm=farm)

    return render(request, 'sows/add_vaccination_plan.html', {
        'form': form,
        'plan': plan,
        'is_edit': True,
    })


@login_required
def delete_vaccination_plan_view(request, plan_id):
    farm = get_current_farm(request)
    plan = VaccinationPlanRepository(farm=farm).get_plan_model_by_id(plan_id)
    if request.method == 'POST':
        plan.delete()
        messages.success(request, "Reguła szczepienia została usunięta.")
    return redirect('vaccination_plans')


@login_required
def sow_detail_view(request, sow_id):
    farm = get_current_farm(request)
    db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

    if request.method == 'POST' and 'edit_sow' in request.POST:
        form = SowForm(request.POST, instance=db_sow)
        if form.is_valid():
            sow_model = form.save()
            log_action(farm=farm, user=request.user, action="UPDATE", obj=sow_model)
            return redirect('sow_detail', sow_id=db_sow.id)
    else:
        form = SowForm(instance=db_sow)

    repo = SowRepository(farm=farm)
    sow = repo.get_sow_by_id(sow_id)

    return render(request, 'sows/sow_detail.html', {'sow': sow, 'form': form})


@login_required
def add_event_view(request, sow_id):
    farm = get_current_farm(request)
    db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

    repo = SowRepository(farm=farm)
    sow = repo.get_sow_by_id(sow_id)
    sow.update_state_for_date(date.today())
    service = SowEventService(farm=farm, repository=repo)

    if request.method == 'POST':
        form = SowEventForm(request.POST, sow_status=sow.status, farm=farm)
        if form.is_valid():
            decision = request.POST.get('farrowing_decision')
            try:
                result = service.create_event(
                    sow=db_sow,
                    sow_status=sow.status,
                    data=form.cleaned_data,
                    farrowing_decision=decision,
                )
            except ValidationError as error:
                form.add_error('event_type', error.messages[0])
                return render(request, 'sows/add_event.html', {'form': form, 'sow': db_sow})
            if result.confirmation_required:
                return render(request, 'sows/add_event.html', {
                    'form': form,
                    'sow': db_sow,
                    'requires_farrowing_confirmation': True,
                    'farrowing_confirmation_message': result.message,
                })
            if result.cancelled or decision == FARROWING_DECISION_CANCEL:
                messages.info(request, "Dodawanie oproszenia zostało anulowane.")
                return redirect('sow_detail', sow_id=sow_id)
            for event in result.created_events:
                log_action(farm=farm, user=request.user, action="CREATE", obj=event)
            return redirect('sow_detail', sow_id=sow_id)
    else:
        requested_event_type = request.GET.get('event_type', '')
        allowed_event_types = {value for value, _label in SowEventModel.EVENT_TYPES}
        initial = {'event_date': date.today()}
        if requested_event_type in allowed_event_types:
            initial['event_type'] = requested_event_type
        form = SowEventForm(sow_status=sow.status, farm=farm, initial=initial)

    return render(request, 'sows/add_event.html', {'form': form, 'sow': db_sow})


@login_required
def bulk_sow_events_view(request):
    farm = get_current_farm(request)
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
                    for row in rows:
                        log_action(
                            farm=farm,
                            user=request.user,
                            action="CREATE",
                            model_label="sows.SowEventModel",
                            object_repr=f"{row.event_type} - {row.event_date} (Maciora: {row.sow.ear_tag})",
                        )
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
    farm = get_current_farm(request)
    service = SowDashboardService(farm=farm)
    context = service.get_notifications()
    sows_to_check = context['sows_to_check_usg']

    if request.method == 'POST':
        for sow in sows_to_check:
            result = request.POST.get(f'result_{sow.id}')

            if result in ['TAK', 'NIE', '?']:
                db_sow = get_object_or_404(SowModel, id=sow.id, farm=farm)
                event = SowEventModel.objects.create(
                    sow=db_sow,
                    event_type='PREGNANCY_CHECK',
                    event_date=date.today(),
                    details={'result': result}
                )
                log_action(farm=farm, user=request.user, action="CREATE", obj=event)
        return redirect('dashboard')

    return render(request, 'sows/bulk_pregnancy.html', {'sows': sows_to_check})


@login_required
def farrowing_panel_view(request):
    farm = get_current_farm(request)
    notifications = SowDashboardService(farm=farm).get_notifications()
    return render(request, 'sows/farrowing_panel.html', {
        'farrowings': notifications['farrowing_due_sows'],
    })


@login_required
def bulk_vaccinate_view(request):
    """Odbiera żądanie z dashboardu, wyświetla ekran potwierdzenia i zapisuje zdarzenia."""
    farm = get_current_farm(request)
    if request.method == 'POST':
        sow_ids = request.POST.getlist('sow_ids')
        vaccine_name = request.POST.get('vaccine_name')
        cycle_id = request.POST.get('cycle_id')

        if request.POST.get('confirm') == 'yes':
            events = _create_vaccination_events(sow_ids, vaccine_name, cycle_id, farm)
            for event in events:
                log_action(farm=farm, user=request.user, action="CREATE", obj=event)
            messages.success(request, f"Zapisano szczepienie dla {len(sow_ids)} macior.")
            return redirect('dashboard')
        else:
            sows = SowModel.objects.filter(id__in=sow_ids, farm=farm)
            return render(request, 'sows/bulk_vaccinate.html', {
                'sows': sows,
                'vaccine_name': vaccine_name,
                'cycle_id': cycle_id
            })

    service = SowDashboardService(farm=farm)
    context = service.get_notifications()
    return render(request, 'sows/bulk_vaccinate.html', {
        'vaccination_groups': context['vaccination_groups'],
        'vaccinations_due_count': context['vaccinations_due_count'],
    })


@login_required
def edit_event_view(request, event_id):
    farm = get_current_farm(request)
    db_event = get_object_or_404(SowEventModel, id=event_id, sow__farm=farm)
    sow_id = db_event.sow.id

    if request.method == 'POST':
        form = SowEventForm(request.POST, instance=db_event, farm=farm)
        if form.is_valid():
            event = form.save()
            log_action(farm=farm, user=request.user, action="UPDATE", obj=event)
            return redirect('sow_detail', sow_id=sow_id)
    else:
        try:
            initial_data = _get_event_initial_data(db_event)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            initial_data = {}
        form = SowEventForm(instance=db_event, initial=initial_data, farm=farm)

    return render(request, 'sows/add_event.html', {
        'form': form,
        'event': db_event,
        'sow': db_event.sow
    })


@login_required
def delete_sow_view(request, sow_id):
    farm = get_current_farm(request)
    if request.method == 'POST':
        db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

        if request.POST.get('archive') == 'on':
            db_sow.is_archived = True
            db_sow.archived_at = timezone.now()
            db_sow.save()
            log_action(farm=farm, user=request.user, action="ARCHIVE", obj=db_sow)
        else:
            representation = str(db_sow)
            object_id = db_sow.pk
            db_sow.delete()
            log_action(farm=farm, user=request.user, action="DELETE", model_label="sows.SowModel", object_id=object_id, object_repr=representation)

        return redirect('dashboard')
    return redirect('sow_detail', sow_id=sow_id)

@login_required
def archived_sows_view(request):
    try:
        service = SowDashboardService(farm=get_current_farm(request))
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

        service = SowDashboardService(farm=get_current_farm(request))
        context = service.get_general_statistics(
            metric_key=metric_key,
            months_limit=months,
            order=order,
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )
        context['date_filter'] = date_range
        context['period_options'] = PERIOD_OPTIONS
        context.update(filter_ui_state(request.GET, {
            'metric': 'Metryka', 'period': 'Okres', 'date_from': 'Od',
            'date_to': 'Do', 'order': 'Ranking',
        }))
        return render(request, 'sows/analytics.html', context)
    except Exception:
        logger.exception("Błąd podczas generowania statystyk")
        return HttpResponse("Błąd podczas generowania statystyk. Szczegóły zapisano w logach aplikacji.", status=500)


@login_required
def delete_event_view(request, event_id):
    if request.method == 'POST':
        farm = get_current_farm(request)
        db_event = get_object_or_404(SowEventModel, id=event_id, sow__farm=farm)
        sow_id = db_event.sow.id
        representation = str(db_event)
        object_id = db_event.pk
        db_event.delete()
        log_action(farm=farm, user=request.user, action="DELETE", model_label="sows.SowEventModel", object_id=object_id, object_repr=representation)
        return redirect('sow_detail', sow_id=sow_id)
    return redirect('dashboard')


def _create_vaccination_events(sow_ids: list, vaccine_name: str, cycle_id: str, farm) -> list:
    """Tworzy zdarzenia szczepienia dla wskazanych macior."""
    events = []
    for s_id in sow_ids:
        db_sow = get_object_or_404(SowModel, id=s_id, farm=farm)
        events.append(SowEventModel.objects.create(
            sow=db_sow,
            event_type='VACCINATION',
            event_date=date.today(),
            details={
                'vaccine_name': vaccine_name,
                'cycle_id': cycle_id
            }
        ))
    return events


def _get_event_initial_data(db_event: SowEventModel) -> dict:
    """Przygotowuje dane początkowe formularza na podstawie typu zdarzenia."""
    return initial_data_from_event_details(db_event.event_type, db_event.details)
