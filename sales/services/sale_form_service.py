from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from sales.forms import SaleClassRowFormSet, empty_sale_row_initials
from sales.models import PigSaleModel, SaleClassRowModel
from sales.services.parsers.factory import SaleSettlementParserFactory


@dataclass
class SalePdfImportResult:
    form_initial: dict = field(default_factory=dict)
    row_initial: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    has_rows: bool = False


class SaleFormService:
    def __init__(self, farm=None):
        self.farm = farm

    @transaction.atomic
    def save_sale(self, form, row_formset, sale: PigSaleModel) -> PigSaleModel:
        saved_sale = form.save(commit=False)
        saved_sale.farm = sale.farm or self.farm
        saved_sale.save()
        self.replace_sale_rows(saved_sale, row_formset)
        return saved_sale

    def replace_sale_rows(self, sale: PigSaleModel, row_formset) -> None:
        sale.rows.all().delete()

        rows = []
        for index, form in enumerate(row_formset.forms, start=1):
            if form.cleaned_data.get('DELETE') or not form.has_row_data():
                continue
            rows.append(SaleClassRowModel(
                sale=sale,
                line_no=form.cleaned_data.get('line_no') or len(rows) + 1 or index,
                meat_class=form.cleaned_data.get('meat_class') or '',
                quantity=form.cleaned_data.get('quantity'),
                weight=form.cleaned_data.get('weight'),
                avg_weight=form.cleaned_data.get('avg_weight'),
                avg_meatiness=form.cleaned_data.get('avg_meatiness'),
                price_per_kg=form.cleaned_data.get('price_per_kg'),
                net_value=form.cleaned_data.get('net_value'),
                vat_value=form.cleaned_data.get('vat_value'),
                gross_value=form.cleaned_data.get('gross_value'),
            ))

        if rows:
            SaleClassRowModel.objects.bulk_create(rows)
            sale.recalculate_from_rows()
            sale.meat_class = rows[0].meat_class or sale.meat_class
            sale.save(update_fields=[
                'quantity',
                'total_weight',
                'meat_class',
                'price_per_kg',
                'net_value',
                'vat_value',
                'gross_value',
            ])
        else:
            sale.recalculate_from_rows()
            sale.save(update_fields=[
                'quantity',
                'total_weight',
                'price_per_kg',
                'net_value',
                'vat_value',
                'gross_value',
            ])

    def parse_pdf_import(self, uploaded_pdf, post_data) -> SalePdfImportResult:
        parsed = SaleSettlementParserFactory.create('pdf').parse(uploaded_pdf)
        initial = self.form_initial_from_post(post_data)
        initial.update(self.without_empty_values(parsed.sale_fields))
        initial['no_settlement'] = False

        return SalePdfImportResult(
            form_initial=initial,
            row_initial=parsed.rows or empty_sale_row_initials(),
            warnings=parsed.warnings,
            has_rows=bool(parsed.rows),
        )

    def initial_rows_for_sale(self, sale: PigSaleModel) -> list[dict]:
        if sale.pk and sale.rows.exists():
            return [
                {
                    'line_no': row.line_no,
                    'meat_class': row.meat_class,
                    'quantity': row.quantity,
                    'weight': row.weight,
                    'avg_weight': row.avg_weight,
                    'avg_meatiness': row.avg_meatiness,
                    'price_per_kg': row.price_per_kg,
                    'net_value': row.net_value,
                    'vat_value': row.vat_value,
                    'gross_value': row.gross_value,
                }
                for row in sale.rows.all()
            ]

        if sale.pk and sale.quantity:
            return [{
                'line_no': 1,
                'meat_class': sale.meat_class,
                'quantity': sale.quantity,
                'weight': sale.total_weight,
                'price_per_kg': sale.price_per_kg,
                'gross_value': sale.total_price,
            }]

        return empty_sale_row_initials()

    @staticmethod
    def form_initial_from_post(post_data) -> dict:
        fields = [
            'sale_date',
            'document_number',
            'tattoo',
            'avg_meatiness_seurop',
            'live_weight',
            'dressing_percentage',
        ]
        initial = {field: post_data.get(field) for field in fields if post_data.get(field)}
        initial['no_settlement'] = post_data.get('no_settlement') == 'on'
        return initial

    @staticmethod
    def without_empty_values(values: dict) -> dict:
        return {key: value for key, value in values.items() if value not in (None, '')}

    @staticmethod
    def row_formset_from_post(post_data):
        if 'rows-TOTAL_FORMS' in post_data:
            return SaleClassRowFormSet(post_data, prefix='rows')

        data = post_data.copy()
        data['rows-TOTAL_FORMS'] = '1'
        data['rows-INITIAL_FORMS'] = '0'
        data['rows-MIN_NUM_FORMS'] = '0'
        data['rows-MAX_NUM_FORMS'] = '1000'
        data['rows-0-line_no'] = '1'
        data['rows-0-meat_class'] = post_data.get('meat_class', '')
        data['rows-0-quantity'] = post_data.get('quantity', '')
        data['rows-0-weight'] = post_data.get('total_weight', '')
        data['rows-0-price_per_kg'] = post_data.get('price_per_kg', '')
        return SaleClassRowFormSet(data, prefix='rows')
