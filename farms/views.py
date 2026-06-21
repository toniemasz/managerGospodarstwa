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
from farms.services.date_range import PERIOD_OPTIONS, parse_date_range


@login_required
def farm_settings_view(request):
    farm = get_current_farm(request)
    settings = get_farm_settings(farm)

    if request.method == 'POST' and 'import_backup' in request.POST:
        import_form = UserBackupImportForm(request.POST, request.FILES)
        if import_form.is_valid():
            try:
                counts = import_user_backup(import_form.cleaned_data['backup_file'], farm)
            except BackupImportError as error:
                messages.error(request, str(error))
            else:
                total = sum(counts.values())
                log_action(farm=farm, user=request.user, action="USER_BACKUP_IMPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm), metadata={"counts": counts})
                messages.success(request, f'Przywrócono dane gospodarstwa ({total} rekordów).')
            return redirect('farm_settings')
        form = FarmSettingsForm(instance=settings, farm=farm)
        csv_import_form = CsvImportForm()
    elif request.method == 'POST' and 'import_csv' in request.POST:
        csv_import_form = CsvImportForm(request.POST, request.FILES)
        if csv_import_form.is_valid():
            try:
                counts = import_csv_archive(csv_import_form.cleaned_data['csv_archive'], farm)
            except BackupImportError as error:
                messages.error(request, str(error))
            else:
                log_action(farm=farm, user=request.user, action="CSV_IMPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm), metadata={"counts": counts})
                messages.success(request, f"Zaimportowano dane CSV ({sum(counts.values())} rekordów).")
                return redirect('farm_settings')
        form = FarmSettingsForm(instance=settings, farm=farm)
        import_form = UserBackupImportForm()
    elif request.method == 'POST':
        form = FarmSettingsForm(request.POST, instance=settings, farm=farm)
        import_form = UserBackupImportForm()
        csv_import_form = CsvImportForm()
        if form.is_valid():
            form.save()
            log_action(farm=farm, user=request.user, action="SETTINGS_UPDATE", obj=settings)
            messages.success(request, "Ustawienia gospodarstwa zostały zapisane.")
            return redirect('farm_settings')
    else:
        form = FarmSettingsForm(instance=settings, farm=farm)
        import_form = UserBackupImportForm()
        csv_import_form = CsvImportForm()

    return render(request, 'farms/settings.html', {'form': form, 'import_form': import_form, 'csv_import_form': csv_import_form})


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
    archive, filename = build_csv_export(farm)
    log_action(farm=farm, user=request.user, action="CSV_EXPORT", model_label="farms.FarmModel", object_id=farm.pk, object_repr=str(farm))
    response = HttpResponse(archive, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def audit_log_view(request):
    farm = get_current_farm(request)
    logs = AuditLogModel.objects.filter(farm=farm).select_related("user")[:250]
    return render(request, "farms/audit_log.html", {"logs": logs})


@login_required
def task_center_view(request):
    context = TaskCenterService(get_current_farm(request)).get_tasks()
    return render(request, "farms/task_center.html", context)


@login_required
def profitability_view(request):
    date_range = parse_date_range(request.GET, default_period="6m")
    context = ProfitabilityAnalyticsService(get_current_farm(request)).calculate(
        date_from=date_range.date_from,
        date_to=date_range.date_to,
    )
    context.update({"date_filter": date_range, "period_options": PERIOD_OPTIONS})
    return render(request, "farms/profitability.html", context)
