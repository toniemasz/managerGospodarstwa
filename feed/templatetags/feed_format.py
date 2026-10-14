from decimal import Decimal

from django import template
from common.number_formatting import format_decimal, format_money, format_percent, to_decimal
from common.units import format_mass


register = template.Library()


@register.filter
def feed_quantity(value):
    return format_mass(value)


@register.filter
def feed_money(value):
    return format_money(value)


@register.filter
def feed_price(value, unit="kg"):
    amount = to_decimal(value)
    if amount is None:
        return "Brak ceny"
    if unit == "ton":
        return f"{format_decimal(amount * Decimal('1000'), max_decimals=2)} PLN/t"
    return f"{format_decimal(amount, max_decimals=5)} PLN/kg"


@register.filter
def feed_percent(value):
    return format_percent(value)
