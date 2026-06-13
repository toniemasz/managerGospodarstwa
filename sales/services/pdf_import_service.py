from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import BinaryIO


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

        first_page = pages[0]
        result = SaleSettlementImport()
        result.sale_fields = self._extract_sale_fields(first_page)
        result.rows = self._extract_main_table_rows(first_page)
        result.summary = self._extract_summary(first_page)

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

    def _extract_sale_fields(self, items: list[PdfTextItem]) -> dict:
        text = '\n'.join(item.text for item in items)
        fields = {}

        slaughter_match = re.search(r'Data uboju:\s*(\d{4}-\d{2}-\d{2})', text)
        if slaughter_match:
            fields['sale_date'] = self._parse_date(slaughter_match.group(1))

        document_match = re.search(r'Dokument nr:\s*([^\n]+)', text)
        if document_match:
            fields['document_number'] = document_match.group(1).strip()

        tattoo_label = self._find_item(items, 'Tatuaż:')
        if tattoo_label:
            tattoo = self._nearest_right_item(items, tattoo_label)
            if tattoo:
                fields['tattoo'] = tattoo.text

        return fields

    def _extract_main_table_rows(self, items: list[PdfTextItem]) -> list[dict]:
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

            row = {
                'line_no': self._parse_int(line_text),
                'meat_class': self._text_in_column(row_items, 'meat_class'),
                'quantity': self._parse_int(self._text_in_column(row_items, 'quantity')),
                'weight': self._parse_decimal(self._text_in_column(row_items, 'weight')),
                'avg_weight': self._parse_decimal(self._text_in_column(row_items, 'avg_weight')),
                'avg_meatiness': self._parse_decimal(self._text_in_column(row_items, 'avg_meatiness')),
                'price_per_kg': self._parse_decimal(self._text_in_column(row_items, 'price_per_kg')),
                'net_value': self._parse_decimal(self._text_in_column(row_items, 'net_value')),
                'vat_value': self._parse_decimal(self._text_in_column(row_items, 'vat_value')),
                'gross_value': self._parse_decimal(self._text_in_column(row_items, 'gross_value')),
            }
            rows.append(row)

        return rows

    def _extract_summary(self, items: list[PdfTextItem]) -> dict:
        summary = {}

        total_label = self._find_item(items, 'Razem:')
        if total_label:
            same_line = self._items_on_same_line(items, total_label.y)
            summary['total_weight'] = self._parse_decimal(self._text_between_x(same_line, 130, 230))
            summary['quantity'] = self._parse_int(self._text_between_x(same_line, 250, 320))
            summary['net_value'] = self._parse_decimal(self._text_between_x(same_line, 430, 520))

        live_label = self._find_item(items, 'Waga żywa:')
        if live_label:
            summary['live_weight'] = self._parse_decimal(self._text_between_x(self._items_on_same_line(items, live_label.y), 130, 230))

        dressing_label = self._find_item(items, 'Wybój:')
        if dressing_label:
            summary['dressing_percentage'] = self._parse_decimal(self._text_between_x(self._items_on_same_line(items, dressing_label.y), 130, 230))

        meatiness_label = self._find_item(items, 'Średnia mięsność dla SEUROP:')
        if meatiness_label:
            summary['avg_meatiness_seurop'] = self._parse_decimal(self._text_between_x(self._items_on_same_line(items, meatiness_label.y), 250, 330))

        gross_label = self._find_item(items, 'Brutto:')
        if gross_label:
            summary['gross_value'] = self._parse_decimal(self._text_between_x(self._items_on_same_line(items, gross_label.y), 430, 520))

        vat_label = self._find_item(items, 'VAT (8%):')
        if vat_label:
            summary['vat_value'] = self._parse_decimal(self._text_between_x(self._items_on_same_line(items, vat_label.y), 430, 520))

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
        try:
            year, month, day = [int(part) for part in value.split('-')]
        except (TypeError, ValueError):
            return None
        return date(year, month, day)

    @staticmethod
    def _parse_decimal(value: str | None) -> Decimal | None:
        if not value:
            return None
        normalized = re.sub(r'[^\d,\.\-]', '', value.replace(' ', '')).replace(',', '.')
        if normalized in ('', '-', '.', '-.'):
            return None
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r'\d+', value.replace(' ', ''))
        return int(match.group(0)) if match else None
