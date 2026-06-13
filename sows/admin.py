from django.contrib import admin
from .models import SowModel, SowEventModel, VaccinationPlanModel


@admin.register(SowModel)
class SowAdmin(admin.ModelAdmin):
    list_display = ('ear_tag', 'farm', 'entry_date', 'is_archived')
    list_filter = ('farm', 'is_archived')
    search_fields = ('ear_tag', 'farm__name', 'farm__owner__username')


@admin.register(SowEventModel)
class SowEventAdmin(admin.ModelAdmin):
    list_display = ('sow', 'event_type', 'event_date')
    list_filter = ('sow__farm', 'event_type')
    search_fields = ('sow__ear_tag', 'sow__farm__name')


@admin.register(VaccinationPlanModel)
class VaccinationPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'farm', 'reminder_days_ahead')
    list_filter = ('farm',)
    search_fields = ('name', 'farm__name', 'farm__owner__username')
