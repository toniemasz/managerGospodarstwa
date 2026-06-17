from django.contrib import admin

from farms.models import FarmModel, FarmSettingsModel


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
        'low_stock_threshold_kg',
    )
    search_fields = ('farm__name', 'farm__owner__username', 'farm__owner__email')
