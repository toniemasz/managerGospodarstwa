from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.utils.formats import number_format


KILOGRAM = "kg"
TONNE = "t"
KILOGRAMS_PER_TONNE = Decimal("1000")
MASS_QUANT = Decimal("0.01")
TONNE_DISPLAY_THRESHOLD_KG = Decimal("1000")
MASS_UNIT_CHOICES = (
    (KILOGRAM, "kg"),
    (TONNE, "t"),
)
PRICE_PER_KG_QUANT = Decimal("0.00001")
PRICE_UNIT_CHOICES = (
    (KILOGRAM, "zł/kg"),
    (TONNE, "zł/t"),
)


def as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        normalized = str(value).strip().replace("\xa0", " ").replace(" ", "").replace(",", ".")
        return Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Nieprawidłowa wartość masy.") from error


def to_kilograms(value, unit: str) -> Decimal:
    amount = as_decimal(value)
    if unit == TONNE:
        amount *= KILOGRAMS_PER_TONNE
    elif unit != KILOGRAM:
        raise ValueError("Nieprawidłowa jednostka masy.")
    return amount.quantize(MASS_QUANT, rounding=ROUND_HALF_UP)


def from_kilograms(value, unit: str) -> Decimal:
    amount = as_decimal(value)
    if unit == TONNE:
        return amount / KILOGRAMS_PER_TONNE
    if unit == KILOGRAM:
        return amount
    raise ValueError("Nieprawidłowa jednostka masy.")


def _as_price_decimal(value) -> Decimal:
    try:
        normalized = str(value).strip().replace("\xa0", " ").replace(" ", "").replace(",", ".")
        return Decimal(normalized)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Podaj prawidłową cenę.") from error


def to_price_per_kg(value, unit: str) -> Decimal:
    """Przelicza dodatnią cenę z wybranej jednostki do kanonicznego zł/kg."""

    amount = _as_price_decimal(value)
    if unit == TONNE:
        amount /= KILOGRAMS_PER_TONNE
    elif unit != KILOGRAM:
        raise ValueError("Nieprawidłowa jednostka ceny.")
    amount = amount.quantize(PRICE_PER_KG_QUANT, rounding=ROUND_HALF_UP)
    if amount <= 0:
        raise ValueError("Cena musi być większa od zera.")
    return amount


def from_price_per_kg(value, unit: str) -> Decimal:
    """Przelicza kanoniczne zł/kg do wartości prezentowanej w wybranej jednostce."""

    amount = _as_price_decimal(value)
    if unit == TONNE:
        return amount * KILOGRAMS_PER_TONNE
    if unit == KILOGRAM:
        return amount
    raise ValueError("Nieprawidłowa jednostka ceny.")


def preferred_mass_unit(value_kg) -> str:
    return TONNE if abs(as_decimal(value_kg)) >= TONNE_DISPLAY_THRESHOLD_KG else KILOGRAM


def mass_input_value(value_kg) -> tuple[str, str]:
    unit = preferred_mass_unit(value_kg)
    value = from_kilograms(value_kg, unit)
    normalized = format(value, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0", unit


def _format_decimal(value: Decimal, max_decimals: int) -> str:
    quantum = Decimal("1") if max_decimals <= 0 else Decimal("1").scaleb(-max_decimals)
    rounded = value.quantize(quantum, rounding=ROUND_HALF_UP)
    formatted = number_format(
        rounded,
        decimal_pos=max_decimals,
        use_l10n=True,
        force_grouping=True,
    )
    if max_decimals:
        formatted = formatted.rstrip("0").rstrip(",").rstrip(".")
    return formatted.replace("\xa0", " ")


def format_mass(value_kg, *, max_decimals: int | None = None, empty="-") -> str:
    if value_kg in (None, ""):
        return empty
    try:
        amount_kg = as_decimal(value_kg)
    except ValueError:
        return empty
    unit = preferred_mass_unit(amount_kg)
    amount = from_kilograms(amount_kg, unit)
    decimals = max_decimals if max_decimals is not None else (5 if unit == TONNE else 2)
    return f"{_format_decimal(amount, decimals)} {unit}"
