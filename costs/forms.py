from django import forms
from django.db.models import Q

from costs.models import CostCategoryModel, CostModel


def _style_fields(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs["class"] = "checkbox-input"
        else:
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} form-control".strip()


class CostCategoryForm(forms.ModelForm):
    class Meta:
        model = CostCategoryModel
        fields = ("name", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        _style_fields(self)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.farm and CostCategoryModel.objects.filter(
            farm=self.farm,
            name__iexact=name,
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Kategoria o tej nazwie już istnieje.")
        return name


class CostForm(forms.ModelForm):
    class Meta:
        model = CostModel
        fields = (
            "date",
            "amount",
            "category",
            "description",
            "document_number",
            "supplier",
            "is_paid",
        )
        widgets = {
            "date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        if farm:
            allowed = Q(is_active=True)
            if self.instance and self.instance.category_id:
                allowed |= Q(pk=self.instance.category_id)
            self.fields["category"].queryset = CostCategoryModel.objects.filter(
                allowed,
                farm=farm,
            ).order_by("name")
        else:
            self.fields["category"].queryset = CostCategoryModel.objects.none()
        self.fields["category"].required = True
        _style_fields(self)

    def clean_category(self):
        category = self.cleaned_data.get("category")
        if category and self.farm and category.farm_id != self.farm.id:
            raise forms.ValidationError("Kategoria nie należy do tego gospodarstwa.")
        return category


class CostFilterForm(forms.Form):
    year = forms.IntegerField(required=False, min_value=2000, max_value=2100, label="Rok")
    date_from = forms.DateField(required=False, label="Od", widget=forms.DateInput(attrs={"type": "date"}))
    date_to = forms.DateField(required=False, label="Do", widget=forms.DateInput(attrs={"type": "date"}))
    category = forms.ModelChoiceField(required=False, queryset=CostCategoryModel.objects.none(), label="Kategoria")
    payment_status = forms.ChoiceField(
        required=False,
        label="Płatność",
        choices=(("", "Wszystkie"), ("paid", "Opłacone"), ("unpaid", "Nieopłacone")),
    )

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm:
            self.fields["category"].queryset = CostCategoryModel.objects.filter(farm=farm).order_by("name")
        _style_fields(self)

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            self.add_error("date_to", "Data końcowa nie może być wcześniejsza niż początkowa.")
        return data
