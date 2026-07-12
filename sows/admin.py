from django.contrib import admin
from .models import (
    MortalityReportModel,
    SowEventModel,
    SowModel,
    VaccinationCycleModel,
    VaccinationPlanModel,
)


@admin.register(SowModel)
class SowAdmin(admin.ModelAdmin):
    list_display = ('ear_tag', 'farm', 'entry_date', 'is_archived', 'archive_reason')
    list_filter = ('farm', 'is_archived', 'archive_reason')
    search_fields = ('ear_tag', 'farm__name', 'farm__owner__username')


@admin.register(SowEventModel)
class SowEventAdmin(admin.ModelAdmin):
    list_display = ('sow', 'event_type', 'event_date')
    list_filter = ('sow__farm', 'event_type')
    search_fields = ('sow__ear_tag', 'sow__farm__name')


@admin.register(VaccinationPlanModel)
class VaccinationPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'farm', 'interval_value', 'interval_unit', 'scope', 'is_active')
    list_filter = ('farm', 'is_active', 'scope', 'schedule_mode')
    search_fields = ('name', 'farm__name', 'farm__owner__username')


@admin.register(VaccinationCycleModel)
class VaccinationCycleAdmin(admin.ModelAdmin):
    list_display = ('plan', 'sow', 'scheduled_date', 'status', 'completed_at', 'skipped_at')
    list_filter = ('plan__farm', 'status', 'scheduled_date')
    search_fields = ('plan__name', 'sow__ear_tag', 'cycle_id')


@admin.register(MortalityReportModel)
class MortalityReportAdmin(admin.ModelAdmin):
    list_display = ('mortality_date', 'mortality_type', 'farm', 'sow', 'quantity', 'created_by')
    list_filter = ('farm', 'mortality_type', 'mortality_date')
    search_fields = ('sow__ear_tag', 'farm__name', 'reason', 'note')
