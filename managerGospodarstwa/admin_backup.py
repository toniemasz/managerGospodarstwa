import logging

from django.contrib import messages
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect

from farms.services.data_backup import (
    BackupImportError,
    build_database_backup,
    load_database_backup_preview,
    restore_database_backup,
    store_database_backup_preview,
)

logger = logging.getLogger(__name__)


@staff_member_required
def admin_database_backup_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Tylko superadministrator może pobrać kopię zapasową bazy danych.")

    archive, zip_filename = build_database_backup()
    log_action(farm=getattr(request, 'farm', None), user=request.user, action="DATABASE_BACKUP", model_label="database", object_repr="Kopia bazy danych")
    response = HttpResponse(archive, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


@staff_member_required
def admin_database_restore_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Tylko superadministrator może przywrócić kopię zapasową bazy danych.")
    if request.method != 'POST':
        return redirect('admin:index')
    if request.POST.get('confirm_empty_restore') == 'on':
        uploaded_file = request.FILES.get('backup_file')
        if not uploaded_file:
            messages.error(request, 'Wybierz plik kopii zapasowej ZIP lub JSON.')
            return redirect('admin:index')
        try:
            restored_count = restore_database_backup(uploaded_file)
        except BackupImportError as error:
            messages.error(request, str(error))
        return redirect('admin:index')
    if request.POST.get('analyze_database_backup'):
        uploaded_file = request.FILES.get('backup_file')
        if not uploaded_file:
            messages.error(request, 'Wybierz plik kopii zapasowej ZIP lub JSON.')
            return redirect('admin:index')
        try:
            token, analysis = store_database_backup_preview(uploaded_file, user=request.user)
        except BackupImportError as error:
            messages.error(request, str(error))
            return redirect('admin:index')
        return admin.site.index(request, extra_context={'database_backup_analysis': analysis, 'database_backup_token': token})
    if request.POST.get('confirmation', '').strip() != 'ZASTĄP CAŁĄ BAZĘ DANYCH' or request.POST.get('confirm_replace') != 'on':
        messages.error(request, 'Potwierdź zastąpienie bazy i wpisz dokładnie: ZASTĄP CAŁĄ BAZĘ DANYCH')
        return redirect('admin:index')
    try:
        cache_key, uploaded_file = load_database_backup_preview(request.POST.get('preview_token', ''), user=request.user)
        restored_count = restore_database_backup(uploaded_file, replace=True)
    except BackupImportError as error:
        messages.error(request, str(error))
    except Exception:
        logger.exception('Nie udało się przywrócić kopii bazy danych')
        messages.error(request, 'Nie udało się przywrócić kopii. Nie zapisano żadnych danych.')
    else:
        logger.warning('Superadministrator %s zastąpił całą bazę z kopii; rekordów: %s', request.user.pk, restored_count)
        messages.success(request, f'Przywrócono kopię bazy ({restored_count} rekordów).')
    return redirect('admin:index')
