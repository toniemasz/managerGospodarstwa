from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils.formats import number_format


def to_decimal(value) -> Decimal | None:
    """Normalizuje wartość liczbową z polskim lub technicznym separatorem."""

    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        normalized = (
            str(value)
            .strip()
            .replace("\xa0", " ")
            .replace(" ", "")
            .replace(",", ".")
        )
        return Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError):
        return None


def format_decimal(value, *, max_decimals: int = 6, empty="-") -> str:
    """Formatuje liczbę po polsku, zachowując tylko znaczące miejsca."""

    amount = to_decimal(value)
    if amount is None:
        return empty
    normalized = amount.normalize()
    decimal_places = (
        0
        if normalized == normalized.to_integral()
        else min(max(0, -normalized.as_tuple().exponent), max_decimals)
    )
    quantum = Decimal("1") if decimal_places == 0 else Decimal("1").scaleb(-decimal_places)
    rounded = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    formatted = number_format(
        rounded,
        decimal_pos=decimal_places,
        use_l10n=True,
        force_grouping=True,
    )
    if decimal_places:
        formatted = formatted.rstrip("0").rstrip(",").rstrip(".")
    return formatted.replace("\xa0", " ")


def format_money(value, *, currency="PLN", empty="-", max_decimals: int = 2) -> str:
    number = format_decimal(value, max_decimals=max_decimals, empty=empty)
    if number == empty:
        return empty
    return f"{number} {currency}".strip()


def format_percent(value, *, empty="-", max_decimals: int = 2) -> str:
    number = format_decimal(value, max_decimals=max_decimals, empty=empty)
    if number == empty:
        return empty
    return f"{number}%"
