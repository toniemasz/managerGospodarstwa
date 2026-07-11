from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


KG_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")
PRICE_QUANT = Decimal("0.00001")


def quantize_kg(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(KG_QUANT, rounding=ROUND_HALF_UP)


def quantize_money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def quantize_price(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)
