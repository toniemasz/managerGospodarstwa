from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template
from django.utils.formats import number_format
from common.units import format_mass


register = template.Library()


def _to_decimal(value):
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _format_decimal(value: Decimal, max_decimals: int) -> str:
    quant = Decimal("1") if max_decimals <= 0 else Decimal("1").scaleb(-max_decimals)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP)
    formatted = number_format(
        rounded,
        decimal_pos=max_decimals,
        use_l10n=True,
        force_grouping=True,
    )
    if max_decimals > 0:
        formatted = formatted.rstrip("0").rstrip(",").rstrip(".")
    return formatted.replace("\xa0", " ")


@register.filter
def feed_quantity(value):
    return format_mass(value)


@register.filter
def feed_money(value):
    amount = _to_decimal(value)
    if amount is None:
        return "-"
    return f"{_format_decimal(amount, 2)} PLN"


@register.filter
def feed_price(value, unit="kg"):
    amount = _to_decimal(value)
    if amount is None:
        return "Brak ceny"
    if unit == "ton":
        return f"{_format_decimal(amount * Decimal('1000'), 2)} PLN/t"
    return f"{_format_decimal(amount, 5)} PLN/kg"


@register.filter
def feed_percent(value):
    amount = _to_decimal(value)
    if amount is None:
        return "-"
    return f"{_format_decimal(amount, 2)}%"
