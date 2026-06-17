import logging

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect

from farms.services.data_backup import (
    BackupImportError,
    build_database_backup,
    restore_database_backup,
)

logger = logging.getLogger(__name__)


@staff_member_required
def admin_database_backup_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Tylko superadministrator może pobrać kopię zapasową bazy danych.")

    archive, zip_filename = build_database_backup()
    response = HttpResponse(archive, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response


@staff_member_required
def admin_database_restore_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Tylko superadministrator może przywrócić kopię zapasową bazy danych.")
    if request.method != 'POST':
        return redirect('admin:index')
    if request.POST.get('confirm_empty_restore') != 'on':
        messages.error(request, 'Potwierdź, że rozumiesz warunek przywracania do pustej bazy.')
        return redirect('admin:index')
    uploaded_file = request.FILES.get('backup_file')
    if not uploaded_file:
        messages.error(request, 'Wybierz plik kopii zapasowej ZIP lub JSON.')
        return redirect('admin:index')
    try:
        restored_count = restore_database_backup(uploaded_file)
    except BackupImportError as error:
        messages.error(request, str(error))
    except Exception:
        logger.exception('Nie udało się przywrócić kopii bazy danych')
        messages.error(request, 'Nie udało się przywrócić kopii. Nie zapisano żadnych danych.')
    else:
        messages.success(request, f'Przywrócono kopię bazy ({restored_count} rekordów).')
    return redirect('admin:index')
