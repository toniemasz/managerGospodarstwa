from io import StringIO, BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone


@staff_member_required
def admin_database_backup_view(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Tylko superadministrator może pobrać kopię zapasową bazy danych.")

    timestamp = timezone.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_filename = f"database_backup_{timestamp}.json"
    zip_filename = f"database_backup_{timestamp}.zip"

    json_buffer = StringIO()
    call_command(
        "dumpdata",
        stdout=json_buffer,
        indent=2,
        natural_foreign=True,
        natural_primary=True,
        exclude=[
            "contenttypes.ContentType",
            "auth.Permission",
            "admin.LogEntry",
            "sessions.Session",
        ],
    )

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as backup_zip:
        backup_zip.writestr(json_filename, json_buffer.getvalue())

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
    return response
