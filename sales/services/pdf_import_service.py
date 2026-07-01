from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import BinaryIO

from sales.number_parsing import parse_polish_decimal, parse_polish_int


@dataclass
class PdfTextItem:
    x: float
    y: float
    text: str


@dataclass
class SaleSettlementImport:
    sale_fields: dict = field(default_factory=dict)
    rows: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class SaleSettlementPdfParser:
    table_columns = {
        'line_no': (40, 65),
        'meat_class': (65, 100),
        'quantity': (100, 135),
        'weight': (135, 195),
        'avg_weight': (195, 245),
        'avg_meatiness': (245, 310),
        'price_per_kg': (310, 360),
        'net_value': (360, 415),
        'vat_value': (415, 470),
        'gross_value': (470, 540),
    }

    def parse(self, file_obj: BinaryIO) -> SaleSettlementImport:
        data = file_obj.read()
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        pages = self._extract_text_pages(data)
        if not pages:
            return SaleSettlementImport(warnings=["Nie udało się odczytać tekstu z PDF."])

        result = SaleSettlementImport()
        result.sale_fields = self._extract_sale_fields(
            [item for page in pages for item in page],
            result.warnings,
        )

        table_page, rows, row_warnings = self._extract_best_table(pages)
        result.rows = rows
        result.warnings.extend(row_warnings)

        if table_page:
            result.summary = self._extract_summary(table_page, result.warnings)
        else:
            result.summary = self._extract_first_summary(pages, result.warnings)

        result.sale_fields.update({
            'avg_meatiness_seurop': result.summary.get('avg_meatiness_seurop'),
            'live_weight': result.summary.get('live_weight'),
            'dressing_percentage': result.summary.get('dressing_percentage'),
        })

        if not result.rows:
            result.warnings.append("Nie znaleziono wierszy głównej tabeli rozliczenia.")

        return result

    def _extract_text_pages(self, data: bytes) -> list[list[PdfTextItem]]:
        pages = []
        streams = re.findall(rb'stream\r?\n(.*?)\r?\nendstream', data, re.S)
        for stream in streams:
            try:
                decoded = zlib.decompress(stream)
            except zlib.error:
                continue
            if b' TJ' not in decoded and b' Tj' not in decoded:
                continue

            items = self._extract_text_items(decoded)
            if items:
                pages.append(items)
        return pages

    def _extract_text_items(self, content: bytes) -> list[PdfTextItem]:
        items = []
        pattern = rb'BT\s+([\-\d\.]+)\s+([\-\d\.]+)\s+Td\s+\[(.*?)\]\s*TJ'
        for match in re.finditer(pattern, content, re.S):
            x = float(match.group(1))
            y = float(match.group(2))
            text = ''.join(self._extract_literals(match.group(3))).strip()
            if text:
                items.append(PdfTextItem(x=x, y=y, text=text))
        return items

    def _extract_literals(self, data: bytes) -> list[str]:
        literals = []
        index = 0
        while index < len(data):
            if data[index:index + 1] != b'(':
                index += 1
                continue

            index += 1
            depth = 1
            buffer = bytearray()
            while index < len(data) and depth:
                char = data[index]
                if char == 92 and index + 1 < len(data):
                    next_char = data[index + 1]
                    simple_escapes = {
                        ord('n'): 10,
                        ord('r'): 13,
                        ord('t'): 9,
                        ord('b'): 8,
                        ord('f'): 12,
                        ord('('): 40,
                        ord(')'): 41,
                        ord('\\'): 92,
                    }
                    if next_char in simple_escapes:
                        buffer.append(simple_escapes[next_char])
                        index += 2
                        continue
                    if 48 <= next_char <= 55:
                        end = index + 1
                        octal = []
                        while end < len(data) and len(octal) < 3 and 48 <= data[end] <= 55:
                            octal.append(chr(data[end]))
                            end += 1
                        buffer.append(int(''.join(octal), 8))
                        index = end
                        continue
                elif char == 40:
                    depth += 1
                    buffer.append(char)
                    index += 1
                    continue
                elif char == 41:
                    depth -= 1
                    if depth == 0:
                        index += 1
                        break
                    buffer.append(char)
                    index += 1
                    continue

                buffer.append(char)
                index += 1

            literals.append(self._decode_literal(bytes(buffer)))
        return literals

    @staticmethod
    def _decode_literal(data: bytes) -> str:
        for encoding in ('utf-16-be', 'utf-8', 'latin2'):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return ''

    def _extract_sale_fields(self, items: list[PdfTextItem], warnings: list[str]) -> dict:
        text = '\n'.join(item.text for item in items)
        fields = {}

        raw_date = self._find_labeled_value(text, (
            'Data uboju',
            'Data sprzedaży',
            'Data sprzedazy',
            'Data dostawy',
        ))
        if raw_date:
            sale_date = self._parse_date(raw_date)
            if sale_date is None:
                warnings.append(
                    f"Nie udało się rozpoznać daty sprzedaży/uboju z PDF: {raw_date}. "
                    "Uzupełnij datę ręcznie przed zapisem."
                )
            else:
                fields['sale_date'] = sale_date
        else:
            warnings.append(
                "Nie znaleziono daty sprzedaży/uboju w PDF. Uzupełnij datę ręcznie przed zapisem."
            )

        document_number = self._find_labeled_value(text, (
            'Dokument nr',
            'Nr dokumentu',
            'Numer dokumentu',
        ))
        if document_number:
            fields['document_number'] = document_number
        else:
            warnings.append(
                "Nie znaleziono numeru dokumentu w PDF. Uzupełnij numer ręcznie przed zapisem."
            )

        tattoo = self._find_labeled_value(text, ('Tatuaż', 'Tatuaz'))
        if tattoo:
            fields['tattoo'] = tattoo
        else:
            tattoo_label = self._find_item(items, 'Tatuaż:')
            if tattoo_label:
                tattoo = self._nearest_right_item(items, tattoo_label)
                if tattoo:
                    fields['tattoo'] = tattoo.text

        return fields

    def _extract_best_table(
        self,
        pages: list[list[PdfTextItem]],
    ) -> tuple[list[PdfTextItem] | None, list[dict], list[str]]:
        best_page = None
        best_rows = []
        best_warnings = []

        for page in pages:
            page_warnings: list[str] = []
            rows = self._extract_main_table_rows(page, page_warnings)
            if len(rows) > len(best_rows):
                best_page = page
                best_rows = rows
                best_warnings = page_warnings

        return best_page, best_rows, best_warnings

    def _extract_first_summary(self, pages: list[list[PdfTextItem]], warnings: list[str]) -> dict:
        for page in pages:
            summary = self._extract_summary(page, warnings)
            if any(value not in (None, '') for value in summary.values()):
                return summary
        return {}

    def _find_labeled_value(self, text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            pattern = rf'{re.escape(label)}[ \t]*:[ \t]*([^\n]*)'
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match and match.group(1).strip():
                return match.group(1).strip()
        return None

    def _extract_main_table_rows(self, items: list[PdfTextItem], warnings: list[str]) -> list[dict]:
        header_y = self._find_header_y(items)
        if header_y is None:
            return []

        summary_y = self._find_summary_y(items)
        lower_bound = summary_y if summary_y is not None else 0
        table_items = [item for item in items if lower_bound < item.y < header_y - 2]
        grouped_rows = self._group_items_by_y(table_items)

        rows = []
        for _, row_items in grouped_rows:
            line_text = self._text_in_column(row_items, 'line_no')
            if not line_text or not line_text.strip().isdigit():
                continue

            row_label = f"wiersz {line_text.strip()}"
            row = {
                'line_no': self._parse_int_field(line_text, 'Lp', warnings, row_label),
                'meat_class': self._text_in_column(row_items, 'meat_class'),
                'quantity': self._parse_int_field(
                    self._text_in_column(row_items, 'quantity'),
                    'ilość',
                    warnings,
                    row_label,
                ),
                'weight': self._parse_decimal_field(
                    self._text_in_column(row_items, 'weight'),
                    'waga',
                    warnings,
                    row_label,
                ),
                'avg_weight': self._parse_decimal_field(
                    self._text_in_column(row_items, 'avg_weight'),
                    'średnia waga',
                    warnings,
                    row_label,
                ),
                'avg_meatiness': self._parse_decimal_field(
                    self._text_in_column(row_items, 'avg_meatiness'),
                    'średnia mięsność',
                    warnings,
                    row_label,
                ),
                'price_per_kg': self._parse_decimal_field(
                    self._text_in_column(row_items, 'price_per_kg'),
                    'cena za kg',
                    warnings,
                    row_label,
                ),
                'net_value': self._parse_decimal_field(
                    self._text_in_column(row_items, 'net_value'),
                    'wartość netto',
                    warnings,
                    row_label,
                ),
                'vat_value': self._parse_decimal_field(
                    self._text_in_column(row_items, 'vat_value'),
                    'VAT',
                    warnings,
                    row_label,
                ),
                'gross_value': self._parse_decimal_field(
                    self._text_in_column(row_items, 'gross_value'),
                    'wartość brutto',
                    warnings,
                    row_label,
                ),
            }
            rows.append(row)

        return rows

    def _extract_summary(self, items: list[PdfTextItem], warnings: list[str]) -> dict:
        summary = {}

        total_label = self._find_item(items, 'Razem:')
        if total_label:
            same_line = self._items_on_same_line(items, total_label.y)
            summary['total_weight'] = self._parse_decimal_field(
                self._text_between_x(same_line, 130, 230),
                'waga razem',
                warnings,
                'podsumowanie',
            )
            summary['quantity'] = self._parse_int_field(
                self._text_between_x(same_line, 250, 320),
                'ilość razem',
                warnings,
                'podsumowanie',
            )
            summary['net_value'] = self._parse_decimal_field(
                self._text_between_x(same_line, 430, 520),
                'wartość netto razem',
                warnings,
                'podsumowanie',
            )

        live_label = self._find_item(items, 'Waga żywa:')
        if live_label:
            summary['live_weight'] = self._parse_decimal_field(
                self._text_between_x(self._items_on_same_line(items, live_label.y), 130, 230),
                'waga żywa',
                warnings,
                'podsumowanie',
            )

        dressing_label = self._find_item(items, 'Wybój:')
        if dressing_label:
            summary['dressing_percentage'] = self._parse_decimal_field(
                self._text_between_x(self._items_on_same_line(items, dressing_label.y), 130, 230),
                'wybój',
                warnings,
                'podsumowanie',
            )

        meatiness_label = self._find_item(items, 'Średnia mięsność dla SEUROP:')
        if meatiness_label:
            summary['avg_meatiness_seurop'] = self._parse_decimal_field(
                self._text_between_x(self._items_on_same_line(items, meatiness_label.y), 250, 330),
                'średnia mięsność SEUROP',
                warnings,
                'podsumowanie',
            )

        gross_label = self._find_item(items, 'Brutto:')
        if gross_label:
            summary['gross_value'] = self._parse_decimal_field(
                self._text_between_x(self._items_on_same_line(items, gross_label.y), 430, 520),
                'wartość brutto',
                warnings,
                'podsumowanie',
            )

        vat_label = self._find_item(items, 'VAT (8%):')
        if vat_label:
            summary['vat_value'] = self._parse_decimal_field(
                self._text_between_x(self._items_on_same_line(items, vat_label.y), 430, 520),
                'VAT',
                warnings,
                'podsumowanie',
            )

        return summary

    def _find_header_y(self, items: list[PdfTextItem]) -> float | None:
        for item in sorted(items, key=lambda i: -i.y):
            if item.text == 'Lp':
                same_line = self._items_on_same_line(items, item.y)
                if any(line_item.text == 'Klasa' for line_item in same_line):
                    return item.y
        return None

    def _find_summary_y(self, items: list[PdfTextItem]) -> float | None:
        item = self._find_item(items, 'Razem:')
        return item.y if item else None

    @staticmethod
    def _group_items_by_y(items: list[PdfTextItem], tolerance: float = 2.0) -> list[tuple[float, list[PdfTextItem]]]:
        rows: list[tuple[float, list[PdfTextItem]]] = []
        for item in sorted(items, key=lambda i: -i.y):
            for index, (row_y, row_items) in enumerate(rows):
                if abs(row_y - item.y) <= tolerance:
                    row_items.append(item)
                    rows[index] = (row_y, sorted(row_items, key=lambda i: i.x))
                    break
            else:
                rows.append((item.y, [item]))
        return rows

    def _text_in_column(self, items: list[PdfTextItem], column: str) -> str:
        left, right = self.table_columns[column]
        return self._text_between_x(items, left, right)

    @staticmethod
    def _text_between_x(items: list[PdfTextItem], left: float, right: float) -> str:
        texts = [item.text for item in sorted(items, key=lambda i: i.x) if left <= item.x < right]
        return ' '.join(texts).strip()

    @staticmethod
    def _items_on_same_line(items: list[PdfTextItem], y: float, tolerance: float = 2.0) -> list[PdfTextItem]:
        return sorted([item for item in items if abs(item.y - y) <= tolerance], key=lambda i: i.x)

    @staticmethod
    def _find_item(items: list[PdfTextItem], text: str) -> PdfTextItem | None:
        return next((item for item in items if item.text.startswith(text)), None)

    @staticmethod
    def _nearest_right_item(items: list[PdfTextItem], label: PdfTextItem) -> PdfTextItem | None:
        candidates = [
            item for item in items
            if abs(item.y - label.y) <= 2.0 and item.x > label.x and item.text != label.text
        ]
        return min(candidates, key=lambda item: item.x, default=None)

    @staticmethod
    def _parse_date(value: str) -> date | None:
        if not value:
            return None

        text = value.strip()
        date_match = re.search(r'\d{4}[-.]\d{2}[-.]\d{2}|\d{2}[-.]\d{2}[-.]\d{4}', text)
        if not date_match:
            return None

        raw_date = date_match.group(0)
        separator = '-' if '-' in raw_date else '.'
        parts = [int(part) for part in raw_date.split(separator)]
        try:
            if parts[0] > 31:
                year, month, day = parts
            else:
                day, month, year = parts
            return date(year, month, day)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_decimal(value: str | None) -> Decimal | None:
        return parse_polish_decimal(value)

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        return parse_polish_int(value)

    def _parse_decimal_field(
        self,
        value: str | None,
        label: str,
        warnings: list[str],
        context: str,
    ) -> Decimal | None:
        parsed = self._parse_decimal(value)
        if parsed is None and value and value.strip():
            warnings.append(
                f"Nie udało się rozpoznać wartości liczbowej pola '{label}' ({context}): {value}. "
                "Uzupełnij ją ręcznie przed zapisem."
            )
        return parsed

    def _parse_int_field(
        self,
        value: str | None,
        label: str,
        warnings: list[str],
        context: str,
    ) -> int | None:
        parsed = self._parse_int(value)
        if parsed is None and value and value.strip():
            warnings.append(
                f"Nie udało się rozpoznać liczby całkowitej pola '{label}' ({context}): {value}. "
                "Uzupełnij ją ręcznie przed zapisem."
            )
        return parsed
