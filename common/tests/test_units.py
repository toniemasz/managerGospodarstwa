from decimal import Decimal

from django import forms

from common.forms import KilogramStorageFormMixin
from common.units import format_mass, mass_input_value, to_kilograms
from farms.templatetags.ui_format import smart_unit
from feed.templatetags.feed_format import feed_quantity


class ExampleMassForm(KilogramStorageFormMixin, forms.Form):
    mass_fields = ("quantity_kg",)
    quantity_kg = forms.DecimalField(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)


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
