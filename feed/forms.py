from decimal import Decimal
from django import forms
from django.db.models import Sum
from django.forms import inlineformset_factory
from django.forms.formsets import DELETION_FIELD_NAME
from .models import IngredientModel, RecipeModel, RecipeItemModel, DeliveryModel, ProductionModel, \
    IngredientPriceConfigModel, ProductionIngredientUsageModel
from feed.domain.rules import LOW_STOCK_THRESHOLD_KG


FORM_FIELD_CLASS = 'form-control'


def _apply_widget_class(field):
    existing = field.widget.attrs.get('class', '')
    field.widget.attrs['class'] = f'{existing} {FORM_FIELD_CLASS}'.strip()


class IngredientForm(forms.ModelForm):
    class Meta:
        model = IngredientModel
        fields = ['name', 'description', 'low_stock_threshold_kg', 'is_in_bin']
        labels = {
            'low_stock_threshold_kg': 'Próg niskiego stanu (kg)',
        }
        widgets = {
            'low_stock_threshold_kg': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
        help_texts = {
            'low_stock_threshold_kg': 'Alert pojawi się, gdy stan tego składnika spadnie poniżej tej wartości. Puste pole oznacza domyślnie 500 kg.',
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        self.fields['low_stock_threshold_kg'].required = False
        self.fields['low_stock_threshold_kg'].initial = LOW_STOCK_THRESHOLD_KG
        if self.farm is not None:
            self.instance.farm = self.farm
        for field in self.fields.values():
            _apply_widget_class(field)

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.farm is not None:
            exists = IngredientModel.objects.filter(farm=self.farm, name__iexact=name).exclude(pk=self.instance.pk).exists()
            if exists:
                raise forms.ValidationError("Taki składnik istnieje już w tym gospodarstwie.")
        return name

    def clean_low_stock_threshold_kg(self):
        return self.cleaned_data.get('low_stock_threshold_kg') or LOW_STOCK_THRESHOLD_KG


class RecipeForm(forms.ModelForm):
    class Meta:
        model = RecipeModel
        fields = ['name']

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        if self.farm is not None:
            self.instance.farm = self.farm

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.farm is not None:
            exists = RecipeModel.objects.filter(farm=self.farm, name__iexact=name).exclude(pk=self.instance.pk).exists()
            if exists:
                raise forms.ValidationError("Taka receptura istnieje już w tym gospodarstwie.")
        return name


class RecipeItemForm(forms.ModelForm):
    class Meta:
        model = RecipeItemModel
        fields = ['ingredient', 'percentage']

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm is not None:
            self.fields['ingredient'].queryset = IngredientModel.objects.filter(farm=farm).order_by('name')


class BaseRecipeItemFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(self.errors):
            return

        total_percentage = Decimal('0.00')
        ingredient_ids = set()

        for form in self.forms:
            # Weryfikacja usunięcia oparta o stałą frameworka
            if self.can_delete and form.cleaned_data.get(DELETION_FIELD_NAME, False):
                continue

            if not form.has_changed() and not form.cleaned_data:
                continue

            percentage = form.cleaned_data.get('percentage')
            if percentage:
                total_percentage += percentage

            ingredient = form.cleaned_data.get('ingredient')
            if ingredient:
                if ingredient.pk in ingredient_ids:
                    raise forms.ValidationError(
                        f"Składnik {ingredient.name} został dodany do receptury więcej niż raz."
                    )
                ingredient_ids.add(ingredient.pk)

        if total_percentage != Decimal('100.00'):
            raise forms.ValidationError(
                f"Suma procentowych udziałów składników musi wynosić równe 100%. "
                f"Obecnie wynosi: {total_percentage}%."
            )


RecipeItemFormSet = inlineformset_factory(
    RecipeModel, RecipeItemModel,
    form=RecipeItemForm,
    formset=BaseRecipeItemFormSet,
    extra=0, can_delete=True
)


class DeliveryForm(forms.ModelForm):
    class Meta:
        model = DeliveryModel
        fields = ['date', 'ingredient', 'quantity_kg', 'price_per_kg']
        widgets = {
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'price_per_kg': forms.NumberInput(attrs={'step': '0.00001'})
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity_kg'].min_value = Decimal('0.01')
        self.fields['price_per_kg'].required = True
        self.fields['price_per_kg'].min_value = Decimal('0.00001')
        if farm is not None:
            self.fields['ingredient'].queryset = IngredientModel.objects.filter(farm=farm).order_by('name')
        for field in self.fields.values():
            _apply_widget_class(field)

    def clean_quantity_kg(self):
        quantity = self.cleaned_data['quantity_kg']
        if self.instance.pk:
            allocated = ProductionIngredientUsageModel.objects.filter(
                delivery=self.instance,
            ).aggregate(total=Sum('quantity_kg'))['total'] or Decimal('0.00')
            if quantity < allocated:
                raise forms.ValidationError(
                    f"Ta dostawa ma już rozliczone {allocated:.2f} kg w produkcji. "
                    "Nie można ustawić mniejszej ilości."
                )
        return quantity

    def clean(self):
        cleaned_data = super().clean()
        ingredient = cleaned_data.get('ingredient')
        if (
            self.instance.pk
            and ingredient is not None
            and ingredient.pk != self.instance.ingredient_id
            and ProductionIngredientUsageModel.objects.filter(delivery=self.instance).exists()
        ):
            self.add_error(
                'ingredient',
                "Nie można zmienić składnika dostawy, która została już rozliczona w produkcji.",
            )
        return cleaned_data


class InventoryAdjustmentForm(forms.Form):
    ingredient = forms.ModelChoiceField(queryset=IngredientModel.objects.none(), label="Składnik")
    movement_date = forms.DateField(
        label="Data korekty",
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    quantity_kg = forms.DecimalField(
        label="Ilość (kg)", min_value=Decimal("0.01"), max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
    )
    direction = forms.ChoiceField(
        label="Typ korekty",
        choices=(("plus", "Zwiększenie stanu"), ("minus", "Zmniejszenie stanu")),
    )
    reason = forms.CharField(label="Powód", max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm is not None:
            self.fields["ingredient"].queryset = IngredientModel.objects.filter(farm=farm).order_by("name")
        for field in self.fields.values():
            _apply_widget_class(field)

    def clean_movement_date(self):
        from django.utils import timezone

        movement_date = self.cleaned_data["movement_date"]
        if movement_date > timezone.localdate():
            raise forms.ValidationError("Data korekty nie może być z przyszłości.")
        return movement_date


class ProductionForm(forms.ModelForm):
    custom_field_prefix = 'custom_percentage_'

    class Meta:
        model = ProductionModel
        fields = ['date', 'time', 'recipe', 'quantity_kg']
        widgets = {
            'date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'})
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        self.recipe_items = []
        self.recipe_item_fields = []
        self._custom_recipe_data = None
        super().__init__(*args, **kwargs)

        if self.farm is not None:
            self.fields['recipe'].queryset = RecipeModel.objects.filter(farm=self.farm).order_by('name')

        for field in self.fields.values():
            _apply_widget_class(field)

        selected_recipe = self._get_selected_recipe()
        if selected_recipe is not None:
            self._add_recipe_percentage_fields(selected_recipe)

    def _get_selected_recipe(self):
        recipe_id = None
        if self.is_bound:
            recipe_id = self.data.get(self.add_prefix('recipe'))
        elif self.instance and self.instance.pk:
            recipe_id = self.instance.recipe_id
        else:
            recipe_id = self.initial.get('recipe')

        if not recipe_id:
            return None

        queryset = RecipeModel.objects.prefetch_related('items__ingredient')
        if self.farm is not None:
            queryset = queryset.filter(farm=self.farm)

        return queryset.filter(pk=recipe_id).first()

    def _add_recipe_percentage_fields(self, recipe):
        custom_data = self.instance.custom_recipe_data or {}
        self.recipe_items = list(recipe.items.select_related('ingredient').order_by('ingredient__name'))

        for item in self.recipe_items:
            field_name = self._field_name_for_item(item)
            initial_value = custom_data.get(str(item.ingredient_id), item.percentage)
            self.fields[field_name] = forms.DecimalField(
                label=item.ingredient.name,
                min_value=Decimal('0.00'),
                max_value=Decimal('100.00'),
                decimal_places=2,
                max_digits=12,
                required=False,
                initial=initial_value,
                widget=forms.NumberInput(attrs={'step': '0.01'}),
            )
            _apply_widget_class(self.fields[field_name])
            self.recipe_item_fields.append({
                'ingredient_name': item.ingredient.name,
                'base_percentage': item.percentage,
                'field': self[field_name],
            })

    def _field_name_for_item(self, item):
        return f'{self.custom_field_prefix}{item.ingredient_id}'

    def clean(self):
        cleaned_data = super().clean()
        recipe = cleaned_data.get('recipe')

        if recipe is None or not self.recipe_items:
            self._custom_recipe_data = None
            return cleaned_data

        if self.farm is not None and recipe.farm_id != self.farm.id:
            self.add_error('recipe', "Wybrana receptura nie należy do Twojego gospodarstwa.")
            return cleaned_data

        total = Decimal('0.00')
        custom_data = {}

        for item in self.recipe_items:
            field_name = self._field_name_for_item(item)
            percentage = cleaned_data.get(field_name)
            if percentage is None:
                percentage = item.percentage
                cleaned_data[field_name] = percentage

            total += percentage
            if percentage != item.percentage:
                custom_data[str(item.ingredient_id)] = str(percentage)

        if abs(total - Decimal('100.00')) > Decimal('0.01'):
            raise forms.ValidationError(f"Proporcje składników muszą sumować się do 100%. Obecnie wynoszą {total}%.")

        self._custom_recipe_data = custom_data or None
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.custom_recipe_data = self._custom_recipe_data
        if commit:
            instance.save()
        return instance


class PriceConfigForm(forms.ModelForm):
    class Meta:
        model = IngredientPriceConfigModel
        fields = ['ingredient', 'price_per_kg']
        widgets = {
            'price_per_kg': forms.NumberInput(attrs={'step': '0.00001'})
        }

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm is not None:
            self.fields['ingredient'].queryset = IngredientModel.objects.filter(farm=farm).order_by('name')


class CalculatorPriceForm(forms.Form):
    price_field_prefix = 'price_'

    def __init__(self, *args, ingredients=None, prices=None, **kwargs):
        self.ingredients = list(ingredients or [])
        self.prices = prices or {}
        super().__init__(*args, **kwargs)

        for ingredient in self.ingredients:
            field_name = self.field_name_for_ingredient(ingredient.id)
            self.fields[field_name] = forms.DecimalField(
                label=ingredient.name,
                min_value=Decimal('0.00001'),
                max_digits=14,
                decimal_places=5,
                required=False,
                error_messages={
                    'invalid': "Podaj poprawną cenę składnika.",
                    'min_value': "Cena składnika musi być większa od 0.",
                },
                widget=forms.NumberInput(attrs={'min': '0.00001', 'step': '0.00001'}),
            )
            self.fields[field_name].initial = self.prices.get(ingredient.id)

    @classmethod
    def field_name_for_ingredient(cls, ingredient_id: int) -> str:
        return f'{cls.price_field_prefix}{ingredient_id}'

    def price_overrides(self) -> dict[int, Decimal]:
        overrides = {}
        for ingredient in self.ingredients:
            field_name = self.field_name_for_ingredient(ingredient.id)
            price = self.cleaned_data.get(field_name)
            if price is not None:
                overrides[ingredient.id] = price
        return overrides
