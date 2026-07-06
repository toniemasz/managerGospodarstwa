from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from farms.forms import CsvImportForm, FarmSettingsForm, UserBackupImportForm
from farms.models import AuditLogModel
from farms.services.audit_log_service import log_action
from farms.services.csv_transfer import build_csv_export, import_csv_archive
from farms.services.current_farm import get_current_farm
from farms.services.data_backup import BackupImportError, build_user_backup, import_user_backup
from farms.services.settings_service import get_farm_settings
from farms.services.task_center import TaskCenterService
from farms.services.profitability import ProfitabilityAnalyticsService
from farms.services.statistics import FarmStatisticsService
from farms.services.accounting_year import get_available_years, parse_accounting_year
from farms.services.module_navigation import module_visibility_groups
from farms.services.farm_dashboard import dashboard_stat_groups
from common.filter_ui import filter_ui_state, parse_filter_date
from farms.services.global_search import build_global_search_context


@login_required
def farm_settings_view(request):
    farm = get_current_farm(request)
    settings = get_farm_settings(farm)

    if request.method == 'POST':
        return _handle_settings_post(request, farm, settings)

    return _render_settings(request, farm, settings)


def _handle_settings_post(request, farm, settings):
    if 'import_backup' in request.POST:
        return _handle_user_backup_import(request, farm, settings)
    if 'import_csv' in request.POST:
        return _handle_csv_import(request, farm, settings)
    return _handle_settings_update(request, farm, settings)


def _handle_user_backup_import(request, farm, settings):
    import_form = UserBackupImportForm(request.POST, request.FILES)
    if not import_form.is_valid():
        return _render_settings(request, farm, settings, import_form=import_form)

    try:
        counts = import_user_backup(import_form.cleaned_data['backup_file'], farm)
    except BackupImportError as error:
        messages.error(request, str(error))
    else:
        total = sum(counts.values())
        log_action(
            farm=farm,
            user=request.user,
            action="USER_BACKUP_IMPORT",
            model_label="farms.FarmModel",
            object_id=farm.pk,
            object_repr=str(farm),
            metadata={"counts": counts},
        )
        messages.success(request, f'Przywrócono dane gospodarstwa ({total} rekordów).')
    return redirect('farm_settings')


def _handle_csv_import(request, farm, settings):
    csv_import_form = CsvImportForm(request.POST, request.FILES)
    if not csv_import_form.is_valid():
        return _render_settings(request, farm, settings, csv_import_form=csv_import_form)

    try:
        counts = import_csv_archive(csv_import_form.cleaned_data['csv_archive'], farm)
    except BackupImportError as error:
        messages.error(request, str(error))
    else:
        log_action(
            farm=farm,
            user=request.user,
            action="CSV_IMPORT",
            model_label="farms.FarmModel",
            object_id=farm.pk,
            object_repr=str(farm),
            metadata={"counts": counts},
        )
        messages.success(request, f"Zaimportowano dane CSV ({sum(counts.values())} rekordów).")
    return redirect('farm_settings')


def _handle_settings_update(request, farm, settings):
    form = FarmSettingsForm(request.POST, instance=settings, farm=farm)
    if form.is_valid():
        saved_settings = form.save()
        log_action(farm=farm, user=request.user, action="SETTINGS_UPDATE", obj=saved_settings)
        messages.success(request, "Ustawienia gospodarstwa zostały zapisane.")
        return redirect('farm_settings')
    return _render_settings(request, farm, settings, form=form)


def _render_settings(request, farm, settings, *, form=None, import_form=None, csv_import_form=None):
    form = form or FarmSettingsForm(instance=settings, farm=farm)
    import_form = import_form or UserBackupImportForm()
    csv_import_form = csv_import_form or CsvImportForm()
    return render(request, 'farms/settings.html', _settings_context(
        form=form,
        import_form=import_form,
        csv_import_form=csv_import_form,
    ))


def _settings_context(*, form, import_form, csv_import_form):
    return {
        'form': form,
        'import_form': import_form,
        'csv_import_form': csv_import_form,
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
