from decimal import Decimal

from farms.templatetags.ui_format import smart_number_value, smart_unit


def test_smart_number_trims_empty_fraction():
    assert smart_number_value(Decimal("2.00")) == "2"
    assert smart_number_value("2,00") == "2"
    assert smart_number_value("2.00") == "2"


def test_smart_number_keeps_meaningful_fraction():
    assert smart_number_value(Decimal("2.50")) == "2,5"


def test_smart_unit_formats_number_with_unit():
    assert smart_unit(Decimal("120.00"), "kg") == "120 kg"
