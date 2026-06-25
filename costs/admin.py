from django.contrib import admin

from costs.models import CostCategoryModel, CostModel


@admin.register(CostCategoryModel)
class CostCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "farm", "is_active", "updated_at")
    list_filter = ("farm", "is_active")
    search_fields = ("name", "farm__name")


@admin.register(CostModel)
class CostAdmin(admin.ModelAdmin):
    list_display = ("date", "description", "farm", "category", "amount", "is_paid")
    list_filter = ("farm", "category", "is_paid", "date")
    search_fields = ("description", "document_number", "supplier", "farm__name")
