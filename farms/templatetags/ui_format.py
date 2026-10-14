from django import template
from common.number_formatting import format_decimal
from common.units import format_mass


register = template.Library()


def smart_number_value(value, max_decimals=6):
    empty = value if value not in (None, "") else "-"
    return format_decimal(value, max_decimals=int(max_decimals), empty=empty)


@register.filter
def smart_number(value, max_decimals=6):
    return smart_number_value(value, max_decimals=max_decimals)


@register.filter
def smart_unit(value, unit):
    if unit == "kg":
        return format_mass(value)
    max_decimals_by_unit = {
        "%": 2,
        "t/t": 3,
        "zł": 2,
        "zł/kg": 2,
        "zł/t": 2,
    }
    number = smart_number_value(value, max_decimals=max_decimals_by_unit.get(unit, 3))
    if number == "-":
        return "-"
    return f"{number} {unit}".strip()
