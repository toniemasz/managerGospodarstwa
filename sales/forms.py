from django import forms
from .models import PigSaleModel

class PigSaleForm(forms.ModelForm):
    class Meta:
        model = PigSaleModel
        fields = ['sale_date', 'meat_class', 'quantity', 'total_weight', 'price_per_kg']
        labels = {
            'sale_date': 'Data sprzedaży',
            'meat_class': 'Klasa mięsności',
            'quantity': 'Ilość sztuk',
            'total_weight': 'Łączna waga (kg)',
            'price_per_kg': 'Cena za 1 kg (PLN)'
        }
        widgets = {
            'sale_date': forms.DateInput(attrs={'type': 'date'}),
        }