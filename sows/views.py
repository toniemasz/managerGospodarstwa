import logging
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.core.exceptions import ValidationError

from .services.sow_dashboard_service import SowDashboardService
from .services.sow_repository import SowRepository, VaccinationPlanRepository
from .services.bulk_event_service import BulkSowEventService
from .services.sow_event_service import FARROWING_DECISION_CANCEL
from .forms import (
    BulkSowEventFormSet,
    MortalityReportForm,
    SowForm,
    SowEventForm,
    VaccinationPlanForm,
    empty_bulk_event_initials,
)
from .models import MortalityReportModel, SowModel, SowEventModel
from common.date_range import PERIOD_OPTIONS, parse_date_range
from common.filter_ui import filter_ui_state
from common.cache import invalidate_farm_cache_on_commit
from farms.services.current_farm import get_current_farm
from farms.services.module_navigation import ModuleNavigationService
from farms.services.audit_log_service import log_action
from farms.services.today_dashboard import TodayDashboardService
from sows.actions.mortality import create_mortality_report
from sows.actions.events import SowEventActions
from sows.actions.vaccinations import VaccinationActionError, VaccinationActions
from sows.domain.event_details import initial_data_from_event_details
from sows.selectors.mortality import mortality_list_context

logger = logging.getLogger(__name__)

@login_required
def modules_home_view(request):
    context = TodayDashboardService(get_current_farm(request)).get_context()
    return render(request, 'farms/today_dashboard.html', context)


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
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
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
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
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
            plan = form.save()
            if plan.scope == plan.SCOPE_ALL:
                plan.selected_sows.clear()
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
            log_action(farm=farm, user=request.user, action="CREATE", obj=plan)
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
            plan = form.save()
            if plan.scope == plan.SCOPE_ALL:
                plan.selected_sows.clear()
            reinclude_sows = form.cleaned_data.get('reinclude_sows')
            if reinclude_sows:
                plan.excluded_sows.remove(*reinclude_sows)
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
            log_action(farm=farm, user=request.user, action="UPDATE", obj=plan)
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
@require_POST
def delete_vaccination_plan_view(request, plan_id):
    farm = get_current_farm(request)
    plan = VaccinationActions(farm, user=request.user).deactivate_plan(plan_id=plan_id)
    log_action(farm=farm, user=request.user, action="UPDATE", obj=plan)
    messages.success(request, "Plan szczepienia został wyłączony. Historia pozostała bez zmian.")
    return redirect('vaccination_plans')


def _vaccination_cycle_post_data(request):
    try:
        return {
            'plan_id': int(request.POST.get('plan_id', '')),
            'sow_id': int(request.POST.get('sow_id', '')),
            'cycle_id': request.POST.get('cycle_id', ''),
            'scheduled_date': date.fromisoformat(request.POST.get('scheduled_date', '')),
        }
    except (TypeError, ValueError) as error:
        raise VaccinationActionError("Nieprawidłowe dane cyklu szczepienia.") from error


@login_required
@require_POST
def record_vaccination_view(request):
    farm = get_current_farm(request)
    try:
        cycle = _vaccination_cycle_post_data(request)
        events = VaccinationActions(farm, user=request.user).record_many(
            plan_id=cycle['plan_id'],
            sow_ids=[cycle['sow_id']],
            cycle_id=cycle['cycle_id'],
            scheduled_date=cycle['scheduled_date'],
            note=request.POST.get('note', '').strip(),
        )
    except VaccinationActionError as error:
        messages.error(request, error.messages[0])
    else:
        log_action(farm=farm, user=request.user, action="CREATE", obj=events[0])
        messages.success(request, "Szczepienie zostało zarejestrowane.")
    return redirect('bulk_vaccinate')


@login_required
@require_POST
def skip_vaccination_view(request):
    farm = get_current_farm(request)
    try:
        cycle = _vaccination_cycle_post_data(request)
        state = VaccinationActions(farm, user=request.user).skip_cycle(
            **cycle,
            note=request.POST.get('note', '').strip(),
        )
    except VaccinationActionError as error:
        messages.error(request, error.messages[0])
    else:
        log_action(farm=farm, user=request.user, action="CREATE", obj=state)
        messages.success(request, "Bieżący cykl został pominięty.")
    return redirect('bulk_vaccinate')


@login_required
@require_POST
def exclude_sow_from_vaccination_view(request):
    farm = get_current_farm(request)
    try:
        cycle = _vaccination_cycle_post_data(request)
        plan = VaccinationActions(farm, user=request.user).exclude_sow(
            plan_id=cycle['plan_id'],
            sow_id=cycle['sow_id'],
        )
    except VaccinationActionError as error:
        messages.error(request, error.messages[0])
    else:
        log_action(farm=farm, user=request.user, action="UPDATE", obj=plan)
        messages.success(request, "Maciora została trwale wyłączona z tego planu.")
    return redirect('bulk_vaccinate')


@login_required
def sow_detail_view(request, sow_id):
    farm = get_current_farm(request)
    db_sow = get_object_or_404(SowModel, id=sow_id, farm=farm)

    if request.method == 'POST' and 'edit_sow' in request.POST:
        form = SowForm(request.POST, instance=db_sow)
        if form.is_valid():
            sow_model = form.save()
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
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
    actions = SowEventActions(farm=farm, user=request.user, repository=repo)

    if request.method == 'POST':
        form = SowEventForm(request.POST, sow_status=sow.status, farm=farm)
        if form.is_valid():
            decision = request.POST.get('farrowing_decision')
            try:
                result = actions.create_event(
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
    requested_event_type = request.GET.get('event_type', '')
    allowed_event_types = {value for value, _label in SowEventModel.EVENT_TYPES}
    if requested_event_type not in allowed_event_types:
        requested_event_type = ''

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
            initial=empty_bulk_event_initials(
                initial_count,
                event_type=requested_event_type,
                event_date=date.today() if is_single else None,
            ),
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
        results_by_sow_id = {
            sow.id: request.POST.get(f'result_{sow.id}')
            for sow in sows_to_check
        }
        events = SowEventActions(farm=farm, user=request.user).bulk_create_pregnancy_checks(
            sows=sows_to_check,
            results_by_sow_id=results_by_sow_id,
        )
        for event in events:
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
        plan_id = request.POST.get('plan_id')
        scheduled_date_value = request.POST.get('scheduled_date')

        if request.POST.get('confirm') == 'yes':
            try:
                events = SowEventActions(farm=farm, user=request.user).bulk_create_vaccinations(
                    sow_ids=sow_ids,
                    vaccine_name=vaccine_name,
                    cycle_id=cycle_id,
                    plan_id=int(plan_id) if plan_id else None,
                    scheduled_date=(date.fromisoformat(scheduled_date_value) if scheduled_date_value else None),
                )
            except (VaccinationActionError, ValueError) as error:
                message = error.messages[0] if isinstance(error, ValidationError) else str(error)
                messages.error(request, message)
                return redirect('bulk_vaccinate')
            for event in events:
                log_action(farm=farm, user=request.user, action="CREATE", obj=event)
            messages.success(request, f"Zapisano szczepienie dla {len(events)} macior.")
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
            event = SowEventActions(farm=farm, user=request.user).update_event(
                event_id=event_id,
                data=form.cleaned_data,
            )
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
            db_sow.archive_reason = SowModel.ARCHIVE_REASON_MANUAL
            db_sow.death_date = None
            db_sow.death_note = ""
            db_sow.save()
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
            log_action(farm=farm, user=request.user, action="ARCHIVE", obj=db_sow)
        else:
            representation = str(db_sow)
            object_id = db_sow.pk
            db_sow.delete()
            invalidate_farm_cache_on_commit(farm, groups=("sows",))
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
def mortality_list_view(request):
    farm = get_current_farm(request)
    context = mortality_list_context(farm, request.GET)
    return render(request, 'sows/mortality_list.html', context)


@login_required
def report_mortality_view(request):
    farm = get_current_farm(request)
    if request.method == 'POST':
        form = MortalityReportForm(request.POST, farm=farm)
        if form.is_valid():
            try:
                result = create_mortality_report(
                    farm=farm,
                    user=request.user,
                    data=form.cleaned_data,
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                _log_mortality_report(farm=farm, user=request.user, result=result)
                if result.report.mortality_type == MortalityReportModel.TYPE_SOW:
                    messages.success(
                        request,
                        "Zgłoszono upadek maciory. Maciora została zarchiwizowana z powodu upadku.",
                    )
                else:
                    messages.success(request, "Zgłoszono upadek zwierząt po odsadzeniu.")
                return redirect('mortality_list')
    else:
        form = MortalityReportForm(
            farm=farm,
            initial={
                'mortality_date': date.today(),
                'mortality_type': request.GET.get('mortality_type', ''),
            },
        )

    return render(request, 'sows/mortality_form.html', {'form': form})


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
        deleted_event = SowEventActions(farm=farm, user=request.user).delete_event(event_id)
        log_action(
            farm=farm,
            user=request.user,
            action="DELETE",
            model_label=deleted_event.model_label,
            object_id=deleted_event.object_id,
            object_repr=deleted_event.object_repr,
        )
        return redirect('sow_detail', sow_id=deleted_event.sow_id)
    return redirect('dashboard')


def _get_event_initial_data(db_event: SowEventModel) -> dict:
    """Przygotowuje dane początkowe formularza na podstawie typu zdarzenia."""
    return initial_data_from_event_details(db_event.event_type, db_event.details)


def _log_mortality_report(*, farm, user, result) -> None:
    report = result.report
    metadata = {
        "mortality_type": report.mortality_type,
        "mortality_date": report.mortality_date.isoformat(),
        "quantity": report.quantity,
        "sow_id": report.sow_id,
        "reason": report.reason,
        "note": report.note,
    }
    log_action(farm=farm, user=user, action="CREATE", obj=report, metadata=metadata)
    if result.archived_sow and report.sow_id:
        log_action(
            farm=farm,
            user=user,
            action="ARCHIVE",
            obj=report.sow,
            metadata={
                "archive_reason": SowModel.ARCHIVE_REASON_DEATH,
                "death_date": report.mortality_date.isoformat(),
                "mortality_report_id": report.id,
            },
        )
