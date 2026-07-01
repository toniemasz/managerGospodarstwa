from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


SPACE_TRANSLATION = str.maketrans({
    '\u00a0': ' ',
    '\u202f': ' ',
    '\u2007': ' ',
})

KNOWN_NUMERIC_UNITS_RE = re.compile(
    r'zł\s*/\s*kg|zl\s*/\s*kg|\bpln\b|\bkg\b|\bszt\.?|zł|zl|%',
    re.IGNORECASE,
)
LETTER_RE = re.compile(r'[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]')


def strip_known_numeric_units(value: str | None) -> str | None:
    if value is None:
        return None

    text = str(value).strip().translate(SPACE_TRANSLATION)
    if not text:
        return ''

    text = KNOWN_NUMERIC_UNITS_RE.sub(' ', text)
    if LETTER_RE.search(text):
        return None
    return text


def parse_polish_decimal(value: object | None) -> Decimal | None:
    if value in (None, ''):
        return None
    if isinstance(value, Decimal):
        return value

    stripped = strip_known_numeric_units(str(value))
    if stripped is None:
        return None

    compact = re.sub(r'\s+', '', stripped)
    if not compact:
        return None

    sign = ''
    if compact[0] in '+-':
        sign = compact[0]
        compact = compact[1:]

    if not compact or any(char in compact for char in '+-'):
        return None
    if not re.fullmatch(r'[\d,.]+', compact):
        return None

    if ',' in compact:
        if compact.count(',') > 1:
            return None
        integer_part, decimal_part = compact.split(',', 1)
        if '.' in decimal_part or not decimal_part.isdigit():
            return None
        normalized = f"{sign}{integer_part.replace('.', '')}.{decimal_part}"
    else:
        if compact.count('.') > 1:
            groups = compact.split('.')
            if not groups[0] or not all(len(group) == 3 and group.isdigit() for group in groups[1:]):
                return None
            compact = ''.join(groups)
        normalized = f"{sign}{compact}"

    if normalized in ('', '+', '-', '.', '+.', '-.'):
        return None

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def parse_polish_int(value: object | None) -> int | None:
    if value in (None, ''):
        return None
    if isinstance(value, int):
        return value

    stripped = strip_known_numeric_units(str(value))
    if stripped is None:
        return None

    compact = re.sub(r'\s+', '', stripped)
    if not compact:
        return None

    sign = ''
    if compact[0] in '+-':
        sign = compact[0]
        compact = compact[1:]

    if sign == '-' or not compact or ',' in compact:
        return None

    if '.' in compact:
        groups = compact.split('.')
        if not groups[0] or not all(len(group) == 3 and group.isdigit() for group in groups[1:]):
            return None
        compact = ''.join(groups)

    if not compact.isdigit():
        return None
    return int(f"{sign}{compact}")
