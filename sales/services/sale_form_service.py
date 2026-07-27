from __future__ import annotations

import re
from dataclasses import dataclass, field

from django.db import transaction

from sales.actions import replace_sale_rows, save_sale as save_sale_action
from sales.forms import SaleClassRowFormSet, empty_sale_row_initials
from sales.models import PigSaleModel, SaleClassRowModel
from sales.services.parsers.factory import SaleSettlementParserFactory


@dataclass
class SalePdfImportResult:
    form_initial: dict = field(default_factory=dict)
    row_initial: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    has_rows: bool = False
    problem_line_numbers: list[str] = field(default_factory=list)

    @property
    def imported_rows_count(self) -> int:
        return len(self.row_initial) if self.has_rows else 0

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def as_feedback(self) -> dict:
        if self.has_rows:
            title = "Import PDF zakończony"
            if self.warning_count:
                summary = (
                    f"Zaimportowano {self.imported_rows_count} wierszy. "
                    f"Liczba uwag do sprawdzenia: {self.warning_count}."
                )
            else:
                summary = (
                    f"Zaimportowano {self.imported_rows_count} wierszy. "
                    "Nie wykryto pól wymagających ręcznej korekty."
                )
        else:
            title = "Import PDF wymaga sprawdzenia"
            summary = (
                "Nie zaimportowano wierszy rozliczenia. "
                f"Liczba uwag do sprawdzenia: {self.warning_count}."
            )

        return {
            'title': title,
            'summary': summary,
            'warnings': self.warnings,
            'warning_count': self.warning_count,
            'has_warnings': bool(self.warnings),
        }


class SaleFormService:
    def __init__(self, farm):
        if farm is None:
            raise ValueError("Zapis sprzedaży wymaga jawnego gospodarstwa.")
        self.farm = farm

    @transaction.atomic
    def save_sale(self, form, row_formset, sale: PigSaleModel) -> PigSaleModel:
        return save_sale_action(
            farm=self.farm,
            form=form,
            row_formset=row_formset,
            sale=sale,
        )

    def replace_sale_rows(self, sale: PigSaleModel, row_formset) -> None:
        replace_sale_rows(sale, row_formset)

    def parse_pdf_import(self, uploaded_pdf, post_data) -> SalePdfImportResult:
        parsed = SaleSettlementParserFactory.create('pdf').parse(uploaded_pdf)
        initial = self.form_initial_from_post(post_data)
        initial.update(self.without_empty_values(parsed.sale_fields))
        initial['no_settlement'] = False
        initial['settlement_process'] = 'pdf'
        initial['settlement_review_required'] = bool(
            parsed.warnings or not parsed.rows
        )

        return SalePdfImportResult(
            form_initial=initial,
            row_initial=parsed.rows or empty_sale_row_initials(),
            warnings=parsed.warnings,
            has_rows=bool(parsed.rows),
            problem_line_numbers=self.warning_line_numbers(parsed.warnings),
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
        initial['settlement_process'] = post_data.get('settlement_process', 'manual')
        return initial

    @staticmethod
    def without_empty_values(values: dict) -> dict:
        return {key: value for key, value in values.items() if value not in (None, '')}

    @staticmethod
    def warning_line_numbers(warnings: list[str]) -> list[str]:
        line_numbers = {
            match
            for warning in warnings
            for match in re.findall(r'\(wiersz\s+(\d+)\)', warning, flags=re.IGNORECASE)
        }
        return sorted(line_numbers, key=lambda value: int(value))

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
