from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from farms.forms import FarmSettingsForm, UserBackupImportForm
from farms.services.current_farm import get_current_farm
from farms.services.data_backup import BackupImportError, build_user_backup, import_user_backup
from farms.services.settings_service import get_farm_settings


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
                messages.success(request, f'Przywrócono dane gospodarstwa ({total} rekordów).')
            return redirect('farm_settings')
        form = FarmSettingsForm(instance=settings, farm=farm)
    elif request.method == 'POST':
        form = FarmSettingsForm(request.POST, instance=settings, farm=farm)
        import_form = UserBackupImportForm()
        if form.is_valid():
            form.save()
            messages.success(request, "Ustawienia gospodarstwa zostały zapisane.")
            return redirect('farm_settings')
    else:
        form = FarmSettingsForm(instance=settings, farm=farm)
        import_form = UserBackupImportForm()

    return render(request, 'farms/settings.html', {'form': form, 'import_form': import_form})


@login_required
def export_user_data_view(request):
    farm = get_current_farm(request)
    archive, zip_filename = build_user_backup(request.user, farm)
    response = HttpResponse(archive, content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
    return response
