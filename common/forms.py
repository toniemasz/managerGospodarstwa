from decimal import Decimal

from django import forms
from django.core.validators import DecimalValidator

from common.units import MASS_UNIT_CHOICES, mass_input_value, to_kilograms


PRICE_UNIT_CHOICES = (("kg", "zł/kg"), ("t", "zł/t"))
KILOGRAMS_PER_TONNE = Decimal("1000")
PRICE_PER_KG_QUANT = Decimal("0.00001")


class UnitChoiceField(forms.ChoiceField):
    """Pole jednostki nie powinno samo oznaczać formularza jako zmienionego."""

    def has_changed(self, initial, data):
        return False


class KilogramStorageFormMixin:
    """Obsługuje masę w kg/t i opcjonalnie cenę w zł/kg lub zł/t."""

    mass_fields: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mass_limits = {}
        for field_name in self.mass_fields:
            if field_name not in self.fields:
                continue
            field = self.fields[field_name]
            if field.label and field.label.endswith(" (kg)"):
                field.label = field.label[:-5]
            unit_name = self.mass_unit_field_name(field_name)
            self._mass_limits[field_name] = (field.min_value, field.max_value)
            field.min_value = None
            field.max_value = None
            if isinstance(field, forms.DecimalField):
                field.decimal_places = max(field.decimal_places or 0, 5)
                if field.max_digits is not None:
                    field.max_digits += 3
                    field.validators = [
                        validator
                        for validator in field.validators
                        if not isinstance(validator, DecimalValidator)
                    ]
                    field.validators.append(DecimalValidator(field.max_digits, field.decimal_places))
            field.widget.attrs.update({"step": "0.00001", "min": "0", "inputmode": "decimal"})
            self.fields[unit_name] = forms.ChoiceField(
                label="Jednostka",
                choices=MASS_UNIT_CHOICES,
                initial="kg",
                required=False,
                widget=forms.Select(attrs={"class": "form-control mass-unit-select"}),
            )
            if not self.is_bound:
                stored_value = self.initial.get(field_name)
                if stored_value in (None, "") and getattr(self, "instance", None) is not None:
                    stored_value = getattr(self.instance, field_name, None)
                if stored_value not in (None, ""):
                    display_value, unit = mass_input_value(stored_value)
                    self.initial[field_name] = display_value
                    self.initial[unit_name] = unit
            self._place_field_after(field_name, unit_name)

        self._configure_price_unit_field()

    @staticmethod
    def mass_unit_field_name(field_name: str) -> str:
        return f"{field_name}_unit"

    def _configure_price_unit_field(self):
        price_field_name = "price_per_kg"
        if price_field_name not in self.fields:
            return

        self.fields[price_field_name].label = "Cena"
        self.fields["price_unit"] = UnitChoiceField(
            label="Jednostka ceny",
            choices=PRICE_UNIT_CHOICES,
            initial="kg",
            required=False,
            widget=forms.Select(attrs={"class": "form-control price-unit-select"}),
        )
        self._place_field_after(price_field_name, "price_unit")

    def _place_field_after(self, field_name, new_field_name):
        ordered = {}
        for name, field in self.fields.items():
            if name == new_field_name:
                continue
            ordered[name] = field
            if name == field_name:
                ordered[new_field_name] = self.fields[new_field_name]
        self.fields = ordered

    def clean(self):
        cleaned_data = super().clean()
        for field_name in self.mass_fields:
            value = cleaned_data.get(field_name)
            unit_name = self.mass_unit_field_name(field_name)
            unit = cleaned_data.get(unit_name) or "kg"
            if value in (None, ""):
                cleaned_data.pop(unit_name, None)
                continue
            try:
                value_kg = to_kilograms(value, unit)
            except ValueError as error:
                self.add_error(field_name, str(error))
                cleaned_data.pop(unit_name, None)
                continue
            min_value, max_value = self._mass_limits.get(field_name, (None, None))
            if min_value is not None and value_kg < min_value:
                self.add_error(field_name, f"Minimalna wartość to {min_value} kg.")
                cleaned_data.pop(unit_name, None)
                continue
            if max_value is not None and value_kg > max_value:
                self.add_error(field_name, f"Maksymalna wartość to {max_value} kg.")
                cleaned_data.pop(unit_name, None)
                continue
            cleaned_data[field_name] = value_kg
            cleaned_data.pop(unit_name, None)

        price = cleaned_data.get("price_per_kg")
        price_unit = cleaned_data.pop("price_unit", None) or "kg"
        if price is not None and price_unit == "t":
            cleaned_data["price_per_kg"] = (
                price / KILOGRAMS_PER_TONNE
            ).quantize(PRICE_PER_KG_QUANT)

        return cleaned_data
