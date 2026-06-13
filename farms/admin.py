from django.contrib import admin

from farms.models import FarmModel


@admin.register(FarmModel)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    search_fields = ('name', 'owner__username', 'owner__email')
