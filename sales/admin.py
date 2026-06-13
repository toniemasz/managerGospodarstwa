from django.contrib import admin
from .models import PigSaleModel, SaleClassRowModel


class SaleClassRowInline(admin.TabularInline):
    model = SaleClassRowModel
    extra = 0


@admin.register(PigSaleModel)
class PigSaleAdmin(admin.ModelAdmin):
    list_display = ('sale_date', 'slaughter_date', 'farm', 'quantity', 'total_weight', 'gross_value', 'settlement_status')
    list_filter = ('farm', 'no_settlement')
    search_fields = ('farm__name', 'farm__owner__username', 'document_number', 'tattoo', 'supplier_name')
    inlines = [SaleClassRowInline]
