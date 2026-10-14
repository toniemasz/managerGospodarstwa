from decimal import Decimal

from common.number_formatting import format_decimal, format_money, format_percent, to_decimal


def test_to_decimal_accepts_polish_grouping_and_decimal_separator():
    assert to_decimal("1 234,50") == Decimal("1234.50")
    assert to_decimal("1\xa0234,50") == Decimal("1234.50")


def test_format_decimal_uses_polish_separator_and_trims_zeroes():
    assert format_decimal(Decimal("1234.5000")) == "1 234,5"
    assert format_decimal(Decimal("0.1234567"), max_decimals=3) == "0,123"


def test_money_and_percent_have_consistent_units():
    assert format_money(Decimal("3093.75"), currency="zł") == "3 093,75 zł"
    assert format_percent(Decimal("12.50")) == "12,5%"


def test_formatters_return_explicit_empty_value():
    assert format_decimal(None) == "-"
    assert format_money("") == "-"
