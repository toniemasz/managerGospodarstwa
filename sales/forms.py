from decimal import Decimal, ROUND_HALF_UP

from django import forms
from django.forms import formset_factory

from .models import PigSaleModel
from .number_parsing import parse_polish_decimal, parse_polish_int
from common.forms import KilogramStorageFormMixin


FORM_FIELD_CLASS = 'form-control'


class PolishDecimalField(forms.DecimalField):
    def prepare_value(self, value):
        if isinstance(value, Decimal):
            places = self.decimal_places if self.decimal_places is not None else 2
            return f"{value:.{places}f}".replace('.', ',')
        return super().prepare_value(value)

    def to_python(self, value):
        if isinstance(value, str) and value.strip():
            parsed = parse_polish_decimal(value)
            if parsed is not None:
                value = str(parsed)
        return super().to_python(value)


class PolishIntegerField(forms.IntegerField):
    def to_python(self, value):
        if isinstance(value, str) and value.strip():
            parsed = parse_polish_int(value)
            if parsed is not None:
                value = str(parsed)
        return super().to_python(value)


class PigSaleForm(KilogramStorageFormMixin, forms.ModelForm):
    mass_fields = ('live_weight',)
    avg_meatiness_seurop = PolishDecimalField(
        label="Średnia mięsność SEUROP (%)",
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0.00'),
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    live_weight = PolishDecimalField(
        label="Waga żywa",
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.00'),
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    dressing_percentage = PolishDecimalField(
        label="Wybój (%)",
        required=False,
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0.00'),
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    settlement_pdf = forms.FileField(
        label="Import rozliczenia PDF",
        required=False,
        widget=forms.FileInput(attrs={'accept': 'application/pdf'})
    )
    settlement_process = forms.ChoiceField(
        label="Sposób uzupełnienia rozliczenia",
        required=False,
        choices=(
            ("manual", "Wpiszę ręcznie"),
            ("pdf", "Importuję PDF"),
            ("later", "Nie mam jeszcze rozliczenia"),
        ),
        widget=forms.RadioSelect,
    )

    class Meta:
        model = PigSaleModel
        fields = [
            'sale_date',
            'document_number',
            'tattoo',
            'no_settlement',
            'settlement_review_required',
            'avg_meatiness_seurop',
            'live_weight',
            'dressing_percentage',
            'settlement_pdf',
        ]
        labels = {
            'sale_date': 'Data sprzedaży',
            'document_number': 'Numer dokumentu',
            'tattoo': 'Tatuaż',
            'supplier_name': 'Dostawca',
            'no_settlement': 'Bez rozliczenia',
            'avg_meatiness_seurop': 'Średnia mięsność SEUROP (%)',
            'live_weight': 'Waga żywa',
            'dressing_percentage': 'Wybój (%)',
        }
        widgets = {
            'sale_date': forms.DateInput(
                    format='%Y-%m-%d',
                    attrs={'type': 'date'}
                ),
            'no_settlement': forms.HiddenInput(),
            'settlement_review_required': forms.HiddenInput(),
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm or getattr(kwargs.get('instance'), 'farm', None)
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial["settlement_process"] = (
                "later"
                if getattr(self.instance, "no_settlement", False)
                else "manual"
            )
        for name, field in self.fields.items():
            if name in {
                'no_settlement',
                'settlement_process',
                'settlement_review_required',
            }:
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {FORM_FIELD_CLASS}'.strip()

    def clean(self):
        data = super().clean()
        process = data.get("settlement_process")
        if not process:
            process = "later" if data.get("no_settlement") else "manual"
            data["settlement_process"] = process
        data["no_settlement"] = process == "later"
        if process != "pdf":
            data["settlement_review_required"] = False
        document_number = (data.get('document_number') or '').strip()
        data['document_number'] = document_number
        sale_date = data.get('sale_date')
        if document_number and sale_date is None:
            self.add_error(
                'sale_date',
                'Podaj datę sprzedaży, aby można było sprawdzić unikalność numeru dokumentu.',
            )
        if self.farm and document_number and sale_date:
            duplicate = PigSaleModel.objects.filter(
                farm=self.farm,
                document_number__iexact=document_number,
                sale_date__year=sale_date.year,
            ).exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error('document_number', 'Numer dokumentu jest już używany w tym roku rozliczeniowym.')
        return data

    def clean_settlement_pdf(self):
        uploaded = self.cleaned_data.get('settlement_pdf')
        if uploaded is None:
            return uploaded
        return self.validate_settlement_pdf(uploaded)

    @staticmethod
    def validate_settlement_pdf(uploaded):
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Plik PDF może mieć maksymalnie 10 MB.")
        if not uploaded.name.lower().endswith('.pdf'):
            raise forms.ValidationError("Wybierz plik z rozszerzeniem .pdf.")
        content_type = getattr(uploaded, 'content_type', '')
        if content_type not in ('application/pdf', 'application/x-pdf'):
            raise forms.ValidationError("Przesłany plik nie ma typu PDF.")
        header = uploaded.read(5)
        uploaded.seek(0)
        if header != b'%PDF-':
            raise forms.ValidationError("Plik nie jest prawidłowym dokumentem PDF.")
        return uploaded


class SaleClassRowForm(KilogramStorageFormMixin, forms.Form):
    mass_fields = ('weight', 'avg_weight')
    line_no = PolishIntegerField(
        label="Lp",
        min_value=1,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'numeric'}),
    )
    meat_class = forms.CharField(label="Klasa", required=False, max_length=20)
    quantity = PolishIntegerField(
        label="Ilość",
        min_value=0,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'numeric'}),
    )
    weight = PolishDecimalField(
        label="Waga",
        min_value=Decimal('0.00'),
        max_digits=10,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    avg_weight = PolishDecimalField(
        label="Śr. waga",
        min_value=Decimal('0.00'),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    avg_meatiness = PolishDecimalField(
        label="Śr. mięsność",
        min_value=Decimal('0.00'),
        max_digits=5,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    price_per_kg = PolishDecimalField(
        label="Cena",
        min_value=Decimal('0.00'),
        max_digits=8,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    net_value = PolishDecimalField(
        label="Wartość",
        min_value=Decimal('0.00'),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    vat_value = PolishDecimalField(
        label="VAT",
        min_value=Decimal('0.00'),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    gross_value = PolishDecimalField(
        label="Wartość brutto",
        min_value=Decimal('0.00'),
        max_digits=12,
        decimal_places=2,
        required=False,
        widget=forms.TextInput(attrs={'inputmode': 'decimal'}),
    )
    accept_calculation_mismatch = forms.BooleanField(
        label="Akceptuję wartości inne niż wynik obliczeń",
        required=False,
    )

    meaningful_fields = [
        'meat_class',
        'quantity',
        'weight',
        'avg_weight',
        'avg_meatiness',
        'price_per_kg',
        'net_value',
        'vat_value',
        'gross_value',
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} settlement-input'.strip()

    def has_row_data(self) -> bool:
        if not hasattr(self, 'cleaned_data'):
            return False
        return any(self.cleaned_data.get(field) not in (None, '') for field in self.meaningful_fields)

    def clean(self):
        data = super().clean()
        if not any(data.get(field) not in (None, "") for field in self.meaningful_fields):
            return data

        self.complete_calculated_values(data)
        mismatches = self.calculation_mismatches(data)
        if mismatches and not data.get("accept_calculation_mismatch"):
            details = "; ".join(mismatches)
            self.add_error(
                "accept_calculation_mismatch",
                (
                    f"Wartości nie zgadzają się z obliczeniami: {details}. "
                    "Popraw kwoty albo jawnie zaakceptuj wartości z dokumentu."
                ),
            )
        return data

    @staticmethod
    def complete_calculated_values(data: dict) -> None:
        """Uzupełnia brakujące wartości wyliczalne bez nadpisywania danych."""
        quantity = data.get("quantity")
        weight = data.get("weight")
        price_per_kg = data.get("price_per_kg")

        if quantity and weight is not None and data.get("avg_weight") is None:
            data["avg_weight"] = (weight / quantity).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

        if (
            weight is not None
            and price_per_kg is not None
            and data.get("net_value") is None
        ):
            data["net_value"] = (weight * price_per_kg).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

        if (
            data.get("net_value") is not None
            and data.get("vat_value") is not None
            and data.get("gross_value") is None
        ):
            data["gross_value"] = (
                data["net_value"] + data["vat_value"]
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def calculation_mismatches(data: dict) -> list[str]:
        """Porównuje podane wartości z obliczeniami, bez zmieniania danych."""
        mismatches = []
        quantity = data.get("quantity")
        weight = data.get("weight")
        avg_weight = data.get("avg_weight")
        price_per_kg = data.get("price_per_kg")
        net_value = data.get("net_value")
        vat_value = data.get("vat_value")
        gross_value = data.get("gross_value")

        if quantity and weight is not None and avg_weight is not None:
            expected_avg = (weight / quantity).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if abs(avg_weight - expected_avg) > Decimal("0.01"):
                mismatches.append(f"średnia waga powinna wynosić {expected_avg}")

        if weight is not None and price_per_kg is not None and net_value is not None:
            expected_net = (weight * price_per_kg).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if abs(net_value - expected_net) > Decimal("0.01"):
                mismatches.append(f"netto powinno wynosić {expected_net}")

        if net_value is not None and vat_value is not None and gross_value is not None:
            expected_gross = (net_value + vat_value).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            if abs(gross_value - expected_gross) > Decimal("0.01"):
                mismatches.append(f"brutto powinno wynosić {expected_gross}")

        return mismatches


class BaseSaleClassRowFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        used_line_numbers = set()
        active_row_count = 0
        for form in self.forms:
            if form.cleaned_data.get('DELETE') or not form.has_row_data():
                continue
            active_row_count += 1
            line_no = form.cleaned_data.get('line_no') or active_row_count
            if line_no in used_line_numbers:
                raise forms.ValidationError(
                    f"Numer wiersza {line_no} występuje w rozliczeniu więcej niż raz."
                )
            used_line_numbers.add(line_no)


SaleClassRowFormSet = formset_factory(
    SaleClassRowForm,
    formset=BaseSaleClassRowFormSet,
    extra=0,
    can_delete=True,
)


def empty_sale_row_initials(count: int = 8) -> list[dict]:
    return [{'line_no': index} for index in range(1, count + 1)]
