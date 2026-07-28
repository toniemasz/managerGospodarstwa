from decimal import Decimal

from django import forms

from common.forms import KilogramStorageFormMixin, PricePerKilogramStorageFormMixin
from common.units import (
    format_mass,
    from_price_per_kg,
    mass_input_value,
    to_kilograms,
    to_price_per_kg,
)
from farms.templatetags.ui_format import smart_unit
from feed.templatetags.feed_format import feed_quantity


class ExampleMassForm(KilogramStorageFormMixin, forms.Form):
    mass_fields = ("quantity_kg",)
    quantity_kg = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)


class ExamplePriceForm(PricePerKilogramStorageFormMixin, forms.Form):
    price_per_kg_fields = ("price_per_kg",)
    price_per_kg = forms.DecimalField(
        min_value=Decimal("0.00001"),
        max_digits=14,
        decimal_places=5,
    )


def test_mass_conversion_always_returns_kilograms_with_database_precision():
    assert to_kilograms("1250,25", "kg") == Decimal("1250.25")
    assert to_kilograms("1,25025", "t") == Decimal("1250.25")
    assert to_kilograms(Decimal("0.00001"), "t") == Decimal("0.01")


def test_mass_form_accepts_tonnes_and_exposes_only_canonical_kilograms():
    form = ExampleMassForm({"quantity_kg": "1.23456", "quantity_kg_unit": "t"})

    assert form.is_valid(), form.errors
    assert form.cleaned_data == {"quantity_kg": Decimal("1234.56")}


def test_mass_form_keeps_legacy_posts_without_unit_as_kilograms():
    form = ExampleMassForm({"quantity_kg": "750.25"})

    assert form.is_valid(), form.errors
    assert form.cleaned_data["quantity_kg"] == Decimal("750.25")


def test_mass_form_initial_value_uses_preferred_display_unit():
    tonnes = ExampleMassForm(initial={"quantity_kg": Decimal("2500.00")})
    kilograms = ExampleMassForm(initial={"quantity_kg": Decimal("500.00")})

    assert tonnes["quantity_kg"].value() == "2.5"
    assert tonnes["quantity_kg_unit"].value() == "t"
    assert kilograms["quantity_kg"].value() == "500"
    assert kilograms["quantity_kg_unit"].value() == "kg"
    assert mass_input_value(Decimal("1000.00")) == ("1", "t")


def test_all_template_mass_formatters_share_the_same_kg_t_rule():
    assert format_mass(Decimal("999.99")).endswith(" kg")
    assert format_mass(Decimal("1000.00")) == "1 t"
    assert format_mass(Decimal("1000.01")) == "1,00001 t"
    assert format_mass(Decimal("1250.00")).endswith(" t")
    assert feed_quantity(Decimal("1250.00")) == format_mass(Decimal("1250.00"))
    assert smart_unit(Decimal("1250.00"), "kg") == format_mass(Decimal("1250.00"))


def test_price_conversion_uses_canonical_price_per_kg_precision():
    assert to_price_per_kg("1,25", "kg") == Decimal("1.25000")
    assert to_price_per_kg("1250", "t") == Decimal("1.25000")
    assert to_price_per_kg("987,50", "t") == Decimal("0.98750")
    assert from_price_per_kg(Decimal("1.25000"), "t") == Decimal("1250.00000")


def test_price_conversion_rejects_unknown_non_positive_and_too_small_values():
    for value, unit in (("1", "l"), ("0", "kg"), ("-1", "t"), ("0.001", "t")):
        try:
            to_price_per_kg(value, unit)
        except ValueError as error:
            assert str(error)
        else:
            raise AssertionError(f"Wartość {value} {unit} powinna zostać odrzucona.")


def test_price_form_converts_tonnes_and_keeps_selected_unit_after_error():
    valid = ExamplePriceForm(
        {"price_per_kg": "1250", "price_per_kg_unit": "t"}
    )
    invalid = ExamplePriceForm(
        {"price_per_kg": "0", "price_per_kg_unit": "t"}
    )

    assert valid.is_valid(), valid.errors
    assert valid.cleaned_data["price_per_kg"] == Decimal("1.25000")
    assert invalid.is_valid() is False
    assert invalid["price_per_kg_unit"].value() == "t"
