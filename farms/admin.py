from django.contrib import admin

from farms.models import AuditLogModel, FarmModel, FarmSettingsModel


@admin.register(FarmModel)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    search_fields = ('name', 'owner__username', 'owner__email')


@admin.register(FarmSettingsModel)
class FarmSettingsAdmin(admin.ModelAdmin):
    list_display = (
        'farm',
        'pregnancy_check_after_days',
        'gestation_days',
        'farrowing_alert_days_ahead',
        'default_production_quantity_kg',
    )
    search_fields = ('farm__name', 'farm__owner__username', 'farm__owner__email')


@admin.register(AuditLogModel)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'farm', 'user', 'action', 'model_label', 'object_repr')
    list_filter = ('farm', 'action', 'model_label')
    search_fields = ('object_repr', 'object_id', 'farm__name', 'user__username')
    readonly_fields = ('farm', 'user', 'action', 'model_label', 'object_id', 'object_repr', 'metadata', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
