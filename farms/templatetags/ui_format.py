from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format
from common.units import format_mass


register = template.Library()


def _to_decimal(value):
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        normalized = str(value).strip().replace("\xa0", " ").replace(" ", "").replace(",", ".")
        return Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError):
        return None


def smart_number_value(value, max_decimals=6):
    amount = _to_decimal(value)
    if amount is None:
        return value if value not in (None, "") else "-"

    normalized = amount.normalize()
    if normalized == normalized.to_integral():
        decimal_places = 0
    else:
        decimal_places = min(max(0, -normalized.as_tuple().exponent), int(max_decimals))

    formatted = number_format(
        amount,
        decimal_pos=decimal_places,
        use_l10n=True,
        force_grouping=True,
    )
    if decimal_places:
        formatted = formatted.rstrip("0").rstrip(",").rstrip(".")
    return formatted.replace("\xa0", " ")


@register.filter
def smart_number(value, max_decimals=6):
    return smart_number_value(value, max_decimals=max_decimals)


@register.filter
def smart_unit(value, unit):
    if unit == "kg":
        return format_mass(value)
    number = smart_number_value(value)
    if number == "-":
        return "-"
    return f"{number} {unit}".strip()
