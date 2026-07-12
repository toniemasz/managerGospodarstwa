from types import SimpleNamespace
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from farms.forms import CsvImportForm, FarmSettingsForm, UserBackupApplyForm, UserBackupImportForm
from farms.models import AuditLogModel
from farms.services.audit_log_service import log_action
from common.cache import invalidate_farm_cache_on_commit
from farms.services.csv_transfer import build_csv_export, import_csv_archive
from farms.services.current_farm import get_current_farm
from farms.services.data_backup import BackupImportError, build_user_backup, import_user_backup, load_user_backup_preview, store_user_backup_preview
from farms.services.settings_service import get_farm_settings
from farms.services.task_center import TaskCenterService
from farms.services.today_dashboard import TodayDashboardService
from farms.services.profitability import ProfitabilityAnalyticsService
from farms.services.statistics import FarmStatisticsService
from farms.services.accounting_year import get_available_years, parse_accounting_year
from farms.services.module_navigation import module_visibility_groups
from farms.services.farm_dashboard import dashboard_stat_groups
from common.filter_ui import filter_ui_state, parse_filter_date
from farms.services.global_search import build_global_search_context
from sows.actions.events import PREGNANCY_CHECK_RESULTS, SowEventActions


@login_required
def farm_settings_view(request):
    farm = get_current_farm(request)
    settings = get_farm_settings(farm)

    if request.method == 'POST':
        return _handle_settings_post(request, farm, settings)

    return _render_settings(request, farm, settings)


def _handle_settings_post(request, farm, settings):
    if 'import_backup' in request.POST:
        return _handle_legacy_user_backup_import(request, farm, settings)
    if 'import_csv' in request.POST:
        return _handle_legacy_csv_import(request, farm, settings)
    if 'analyze_backup' in request.POST:
        return _handle_user_backup_preview(request, farm, settings)
    if 'apply_backup' in request.POST:
        return _handle_user_backup_apply(request, farm, settings)
    return _handle_settings_update(request, farm, settings)


def _handle_legacy_csv_import(request, farm, settings):
    form = CsvImportForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, 'Nieprawidłowy plik importu CSV.')
        return redirect('farm_settings')
    try:
        counts = import_csv_archive(form.cleaned_data['csv_archive'], farm)
    except BackupImportError as error:
        messages.error(request, str(error))
    else:
        log_action(farm=farm, user=request.user, action="CSV_IMPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm), metadata={"counts": counts})
        messages.success(request, f"Zaimportowano dane CSV ({sum(counts.values())} rekordów).")
    return redirect('farm_settings')


def _handle_legacy_user_backup_import(request, farm, settings):
    form = UserBackupImportForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_settings(request, farm, settings, import_form=form)
    try:
        counts = import_user_backup(form.cleaned_data['backup_file'], farm)
    except BackupImportError as error:
        messages.error(request, str(error))
    else:
        log_action(farm=farm, user=request.user, action="USER_BACKUP_IMPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm), metadata={"counts": counts, "mode": "LEGACY_EMPTY"})
        invalidate_farm_cache_on_commit(farm)
        messages.success(request, f'Przywrócono dane gospodarstwa ({sum(counts.values())} rekordów).')
    return redirect('farm_settings')


def _handle_user_backup_preview(request, farm, settings):
    import_form = UserBackupImportForm(request.POST, request.FILES)
    if not import_form.is_valid():
        return _render_settings(request, farm, settings, import_form=import_form)
    try:
        token, analysis = store_user_backup_preview(import_form.cleaned_data['backup_file'], user=request.user, farm=farm)
    except BackupImportError as error:
        messages.error(request, str(error))
        return redirect('farm_settings')
    apply_form = UserBackupApplyForm(initial={'preview_token': token, 'import_mode': 'ADD_MISSING'})
    return _render_settings(request, farm, settings, import_form=UserBackupImportForm(), apply_form=apply_form, backup_analysis=analysis)


def _handle_user_backup_apply(request, farm, settings):
    apply_form = UserBackupApplyForm(request.POST)
    if not apply_form.is_valid():
        try:
            _, uploaded = load_user_backup_preview(request.POST.get('preview_token', ''), user=request.user, farm=farm)
            from farms.services.data_backup import analyze_user_backup
            analysis = analyze_user_backup(uploaded, farm)
        except BackupImportError:
            analysis = None
        return _render_settings(request, farm, settings, apply_form=apply_form, backup_analysis=analysis)
    try:
        cache_key, uploaded = load_user_backup_preview(apply_form.cleaned_data['preview_token'], user=request.user, farm=farm)
        counts = import_user_backup(uploaded, farm, mode=apply_form.cleaned_data['import_mode'])
    except BackupImportError as error:
        messages.error(request, str(error))
    else:
        log_action(
            farm=farm,
            user=request.user,
            action="USER_BACKUP_IMPORT",
            model_label="farms.FarmModel",
            object_id=farm.pk,
            object_repr=str(farm),
            metadata={"counts": counts, "mode": apply_form.cleaned_data['import_mode']},
        )
        invalidate_farm_cache_on_commit(farm)
        from farms.models import BackupImportPreviewModel
        BackupImportPreviewModel.objects.filter(pk=cache_key).delete()
        messages.success(request, f"Zakończono import danych ({sum(counts.values())} rekordów).")
    return redirect('farm_settings')


def _handle_settings_update(request, farm, settings):
    form = FarmSettingsForm(request.POST, instance=settings, farm=farm)
    if form.is_valid():
        saved_settings = form.save()
        invalidate_farm_cache_on_commit(farm, groups=("settings",))
        log_action(farm=farm, user=request.user, action="SETTINGS_UPDATE", obj=saved_settings)
        messages.success(request, "Ustawienia gospodarstwa zostały zapisane.")
        return redirect('farm_settings')
    return _render_settings(request, farm, settings, form=form)


def _render_settings(request, farm, settings, *, form=None, import_form=None, apply_form=None, backup_analysis=None):
    form = form or FarmSettingsForm(instance=settings, farm=farm)
    import_form = import_form or UserBackupImportForm()
    return render(request, 'farms/settings.html', _settings_context(
        form=form,
        import_form=import_form,
        apply_form=apply_form,
        backup_analysis=backup_analysis,
    ))


def _settings_context(*, form, import_form, apply_form=None, backup_analysis=None):
    return {
        'form': form,
        'import_form': import_form,
        'apply_form': apply_form,
        'backup_analysis': backup_analysis,
        'module_visibility_groups': module_visibility_groups(form),
        'dashboard_stat_groups': dashboard_stat_groups(form),
    }


@login_required
def export_user_data_view(request):
    farm = get_current_farm(request)
    archive, zip_filename = build_user_backup(request.user, farm)
    log_action(farm=farm, user=request.user, action="USER_BACKUP_EXPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm))
    response = HttpResponse(archive, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
    return response


@login_required
def export_csv_view(request):
    farm = get_current_farm(request)
    accounting_year = parse_accounting_year(request.GET)
    archive, filename = build_csv_export(farm, year=accounting_year.year)
    log_action(farm=farm, user=request.user, action="CSV_EXPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm))
    response = HttpResponse(archive, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def audit_log_view(request):
    farm = get_current_farm(request)
    logs = AuditLogModel.objects.filter(farm=farm).select_related("user")
    action = request.GET.get('action', '')
    date_from = parse_filter_date(request.GET.get('date_from'))
    date_to = parse_filter_date(request.GET.get('date_to'))
    if action:
        logs = logs.filter(action=action)
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)
    context = {
        "logs": logs[:250],
        "audit_actions": AuditLogModel.objects.filter(farm=farm).values_list('action', flat=True).distinct().order_by('action'),
    }
    context.update(filter_ui_state(request.GET, {'action': 'Akcja', 'date_from': 'Od', 'date_to': 'Do'}))
    return render(request, "farms/audit_log.html", context)


@login_required
def task_center_view(request):
    context = TaskCenterService(get_current_farm(request)).get_tasks()
    active_tab = request.GET.get("tab", "production")
    if active_tab not in context["tabs"]:
        active_tab = "production"
    context["active_tab"] = active_tab
    context["active_tab_data"] = context["tabs"][active_tab]
    return render(request, "farms/task_center.html", context)


@login_required
def complete_today_tasks_view(request):
    if request.method != 'POST':
        return redirect('modules_home')

    farm = get_current_farm(request)
    selected_task_ids = list(dict.fromkeys(task_id for task_id in request.POST.getlist('task_ids') if task_id))
    if not selected_task_ids:
        messages.error(request, "Zaznacz przynajmniej jedno zadanie do zatwierdzenia.")
        return redirect('modules_home')

    tasks_by_id = TodayDashboardService(farm).completable_tasks_by_id()
    selected_tasks = [tasks_by_id[task_id] for task_id in selected_task_ids if task_id in tasks_by_id]
    if not selected_tasks:
        messages.error(request, "Nie znaleziono zadań możliwych do szybkiego zatwierdzenia.")
        return redirect('modules_home')

    note = (request.POST.get('completion_note') or '').strip()[:500]
    try:
        created_events = _complete_today_tasks(
            farm=farm,
            user=request.user,
            tasks=selected_tasks,
            post_data=request.POST,
            note=note,
        )
    except ValidationError as error:
        messages.error(request, error.messages[0] if error.messages else str(error))
        return redirect('modules_home')

    for event in created_events:
        log_action(farm=farm, user=request.user, action="CREATE", obj=event)

    messages.success(request, f"Zatwierdzono {len(created_events)} zadań z listy na dziś.")
    return redirect('modules_home')


def _complete_today_tasks(*, farm, user, tasks, post_data, note):
    _validate_today_tasks(tasks=tasks, post_data=post_data)

    actions = SowEventActions(farm=farm, user=user)
    created_events = []
    event_date = timezone.localdate()

    with transaction.atomic():
        for task in tasks:
            metadata = task["metadata"]
            kind = metadata.get("kind")
            sow_id = metadata.get("sow_id")

            if kind == "vaccination":
                created_events.extend(actions.bulk_create_vaccinations(
                    sow_ids=[sow_id],
                    vaccine_name=metadata.get("vaccine_name") or "",
                    cycle_id=metadata.get("cycle_id") or "",
                    plan_id=metadata.get("plan_id"),
                    scheduled_date=date.fromisoformat(metadata["scheduled_date"]),
                    event_date=event_date,
                    note=note,
                ))
            elif kind == "ultrasound":
                result = post_data.get(f"pregnancy_result_{task['task_id']}")
                created_events.extend(actions.bulk_create_pregnancy_checks(
                    sows=[SimpleNamespace(id=sow_id)],
                    results_by_sow_id={sow_id: result},
                    event_date=event_date,
                ))

    return created_events


def _validate_today_tasks(*, tasks, post_data):
    for task in tasks:
        metadata = task["metadata"]
        kind = metadata.get("kind")
        if not metadata.get("sow_id"):
            raise ValidationError("Nie można zatwierdzić zadania bez przypisanej maciory.")
        if kind == "vaccination":
            if not all(metadata.get(field) for field in (
                "vaccine_name", "cycle_id", "plan_id", "scheduled_date"
            )):
                raise ValidationError("Nie można zatwierdzić szczepienia bez planu, terminu albo cyklu.")
        elif kind == "ultrasound":
            result = post_data.get(f"pregnancy_result_{task['task_id']}")
            if result not in PREGNANCY_CHECK_RESULTS:
                raise ValidationError("Wybierz wynik USG dla każdego zaznaczonego badania.")
        else:
            raise ValidationError("To zadanie wymaga uzupełnienia w dedykowanym formularzu.")


@login_required
def profitability_view(request):
    farm = get_current_farm(request)
    accounting_year = parse_accounting_year(request.GET)
    context = ProfitabilityAnalyticsService(get_current_farm(request)).calculate(
        date_from=accounting_year.date_from,
        date_to=accounting_year.date_to,
    )
    context.update({
        "selected_year": accounting_year.year,
        "available_years": get_available_years(farm),
    })
    context.update(filter_ui_state(request.GET, {'year': 'Rok'}))
    return render(request, "farms/profitability.html", context)


@login_required
def statistics_view(request):
    farm = get_current_farm(request)
    accounting_year = parse_accounting_year(request.GET)
    context = FarmStatisticsService(farm).calculate(
        date_from=accounting_year.date_from,
        date_to=accounting_year.date_to,
    )
    context.update({
        "selected_year": accounting_year.year,
        "available_years": get_available_years(farm),
        "statistic_links": FarmStatisticsService.statistic_links(),
    })
    context.update(filter_ui_state(request.GET, {'year': 'Rok'}))
    return render(request, "farms/statistics.html", context)


@login_required
def global_search_view(request):
    farm = get_current_farm(request)
    context = build_global_search_context(
        farm,
        request.GET.get("q", ""),
        active_url_name=getattr(getattr(request, "resolver_match", None), "url_name", ""),
    )
    return render(request, "farms/search_results.html", context)
