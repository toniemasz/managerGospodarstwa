from django import forms
from django.forms import inlineformset_factory
from .models import IngredientModel, RecipeModel, RecipeItemModel, DeliveryModel, ProductionModel, IngredientPriceConfigModel

class IngredientForm(forms.ModelForm):
    class Meta:
        model = IngredientModel
        fields = ['name', 'description']

class RecipeForm(forms.ModelForm):
    class Meta:
        model = RecipeModel
        fields = ['name']


RecipeItemFormSet = inlineformset_factory(
    RecipeModel, RecipeItemModel,
    fields=['ingredient', 'percentage'],
    extra=5, can_delete=True
)

class DeliveryForm(forms.ModelForm):
    class Meta:
        model = DeliveryModel
        fields = ['date', 'ingredient', 'quantity_kg', 'price_per_kg']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

class ProductionForm(forms.ModelForm):
    class Meta:
        model = ProductionModel
        fields = ['date', 'recipe', 'quantity_kg']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

class PriceConfigForm(forms.ModelForm):
    class Meta:
        model = IngredientPriceConfigModel
        fields = ['ingredient', 'price_per_kg']