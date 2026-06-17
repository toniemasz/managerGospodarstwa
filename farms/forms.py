from django import forms

from farms.models import FarmSettingsModel


class FarmSettingsForm(forms.ModelForm):
    farm_name = forms.CharField(label="Nazwa gospodarstwa", max_length=150)

    class Meta:
        model = FarmSettingsModel
        fields = [
            'farm_name',
            'pregnancy_check_after_days',
            'gestation_days',
            'farrowing_alert_days_ahead',
            'vaccination_alert_days_ahead',
            'low_stock_threshold_kg',
            'default_production_quantity_kg',
            'allow_farrowing_without_pregnancy_check',
            'ask_before_auto_pregnancy_check',
        ]
        labels = {
            'pregnancy_check_after_days': 'Dni do badania USG',
            'gestation_days': 'Długość ciąży',
            'farrowing_alert_days_ahead': 'Dni alertu przed oproszeniem',
            'vaccination_alert_days_ahead': 'Dni alertu szczepienia',
            'low_stock_threshold_kg': 'Próg niskiego stanu magazynu',
            'default_production_quantity_kg': 'Domyślna ilość śrutowania',
            'allow_farrowing_without_pregnancy_check': 'Pozwalać na oproszenie bez badania',
            'ask_before_auto_pregnancy_check': 'Pytać o automatyczne badanie TAK',
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        initial = kwargs.pop('initial', {})
        if farm is not None:
            initial = {**initial, 'farm_name': farm.name}
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = f'{existing} checkbox-input'.strip()
            else:
                field.widget.attrs['class'] = f'{existing} form-control'.strip()

    def save(self, commit=True):
        settings = super().save(commit=False)
        if self.farm is not None:
            self.farm.name = self.cleaned_data['farm_name']
            if commit:
                self.farm.save(update_fields=['name'])
            settings.farm = self.farm
        if commit:
            settings.save()
        return settings
