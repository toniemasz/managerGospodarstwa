from decimal import Decimal

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

    class Meta:
        model = PigSaleModel
        fields = [
            'sale_date',
            'document_number',
            'tattoo',
            'no_settlement',
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
            'no_settlement': forms.CheckboxInput(attrs={'class': 'checkbox-input'}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm or getattr(kwargs.get('instance'), 'farm', None)
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == 'no_settlement':
                continue
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} {FORM_FIELD_CLASS}'.strip()

    def clean(self):
        data = super().clean()
        document_number = (data.get('document_number') or '').strip()
        sale_date = data.get('sale_date')
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


SaleClassRowFormSet = formset_factory(SaleClassRowForm, extra=0, can_delete=True)


def empty_sale_row_initials(count: int = 8) -> list[dict]:
    return [{'line_no': index} for index in range(1, count + 1)]
