import json
from decimal import Decimal
from django import forms
from django.forms import inlineformset_factory
from django.forms.formsets import DELETION_FIELD_NAME
from .models import IngredientModel, RecipeModel, RecipeItemModel, DeliveryModel, ProductionModel, \
    IngredientPriceConfigModel


class IngredientForm(forms.ModelForm):
    class Meta:
        model = IngredientModel
        # Dodane pole is_in_bin, aby w panelu decydować czy to silos czy worek
        fields = ['name', 'description', 'is_in_bin']


class RecipeForm(forms.ModelForm):
    class Meta:
        model = RecipeModel
        fields = ['name']


class BaseRecipeItemFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        total_percentage = Decimal('0.00')

        for form in self.forms:
            # Weryfikacja usunięcia oparta o stałą frameworka
            if self.can_delete and form.cleaned_data.get(DELETION_FIELD_NAME, False):
                continue

            if not form.has_changed() and not form.cleaned_data:
                continue

            percentage = form.cleaned_data.get('percentage')
            if percentage:
                total_percentage += percentage

        if total_percentage != Decimal('100.00'):
            raise forms.ValidationError(
                f"Suma procentowych udziałów składników musi wynosić równe 100%. "
                f"Obecnie wynosi: {total_percentage}%."
            )


RecipeItemFormSet = inlineformset_factory(
    RecipeModel, RecipeItemModel,
    formset=BaseRecipeItemFormSet,
    fields=['ingredient', 'percentage'],
    extra=0, can_delete=True
)


class DeliveryForm(forms.ModelForm):
    class Meta:
        model = DeliveryModel
        fields = ['date', 'ingredient', 'quantity_kg', 'price_per_kg']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'price_per_kg': forms.NumberInput(attrs={'step': '0.00001'})
        }

class ProductionForm(forms.ModelForm):
    class Meta:
        model = ProductionModel
        fields = ['date', 'time', 'recipe', 'quantity_kg', 'custom_recipe_data']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'time': forms.TimeInput(attrs={'type': 'time'})
        }

    def clean_custom_recipe_data(self):
        data = self.cleaned_data.get('custom_recipe_data')
        if not data:
            return data

        try:
            # Konwersja ze stringa, jeśli dane przyszły np. z ukrytego inputa przez JS
            if isinstance(data, str):
                data = json.loads(data)

            total = sum(float(val) for val in data.values())
            # Dopuszczamy minimalny błąd precyzji obliczeń zmiennoprzecinkowych z JS (0.01)
            if abs(total - 100.0) > 0.01:
                raise forms.ValidationError(f"Zmienione proporcje muszą sumować się do 100%. Podano: {total:.2f}%.")
            return data
        except (ValueError, TypeError):
            raise forms.ValidationError("Przekazano nieprawidłowy format modyfikacji receptury.")


class PriceConfigForm(forms.ModelForm):
    class Meta:
        model = IngredientPriceConfigModel
        fields = ['ingredient', 'price_per_kg']
        widgets = {
            'price_per_kg': forms.NumberInput(attrs={'step': '0.00001'})
        }