from django import forms

from farms.dashboard_registry import DASHBOARD_STAT_DEFINITIONS, normalize_dashboard_stats
from farms.models import FarmSettingsModel
from farms.module_registry import MODULE_DEFINITIONS
from farms.services.module_navigation import normalize_nav_modules, normalize_visible_modules
from common.forms import KilogramStorageFormMixin


class FarmSettingsForm(KilogramStorageFormMixin, forms.ModelForm):
    mass_fields = ('default_production_quantity_kg',)
    farm_name = forms.CharField(label="Nazwa gospodarstwa", max_length=150)

    class Meta:
        model = FarmSettingsModel
        fields = [
            'farm_name',
            'interface_scale',
            'theme',
            'font_scale',
            'pregnancy_check_after_days',
            'gestation_days',
            'farrowing_alert_days_ahead',
            'vaccination_alert_days_ahead',
            'default_production_quantity_kg',
            'allow_farrowing_without_pregnancy_check',
            'ask_before_auto_pregnancy_check',
        ]
        labels = {
            'interface_scale': 'Gęstość interfejsu',
            'theme': 'Motyw',
            'font_scale': 'Rozmiar tekstu',
            'pregnancy_check_after_days': 'Dni do badania USG',
            'gestation_days': 'Długość ciąży',
            'farrowing_alert_days_ahead': 'Dni alertu przed oproszeniem',
            'vaccination_alert_days_ahead': 'Dni alertu szczepienia',
            'default_production_quantity_kg': 'Domyślna ilość śrutowania',
            'allow_farrowing_without_pregnancy_check': 'Pozwalać na oproszenie bez badania',
            'ask_before_auto_pregnancy_check': 'Pytać o automatyczne badanie TAK',
        }
        widgets = {
            'interface_scale': forms.RadioSelect(),
            'theme': forms.RadioSelect(),
            'font_scale': forms.NumberInput(attrs={
                'min': 20,
                'max': 200,
                'step': 1,
                'inputmode': 'numeric',
                'data-font-scale-number': 'true',
            }),
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        initial = kwargs.pop('initial', {})
        if farm is not None:
            initial = {**initial, 'farm_name': farm.name}
        kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        visible = normalize_visible_modules(getattr(self.instance, 'visible_modules', None))
        nav_modules = normalize_nav_modules(
            getattr(self.instance, 'nav_modules', None),
            visible_keys=visible,
        )
        dashboard_stats = normalize_dashboard_stats(
            getattr(self.instance, 'dashboard_stats', None),
            visible_keys=visible,
        )
        for module in MODULE_DEFINITIONS:
            if module['key'] == 'settings':
                continue
            self.fields[f"show_{module['key']}"] = forms.BooleanField(
                required=False,
                label=module['title'],
                initial=module['key'] in visible,
                widget=forms.CheckboxInput(attrs={'class': 'checkbox-input'}),
            )
            self.fields[f"nav_{module['key']}"] = forms.BooleanField(
                required=False,
                label=f"{module['title']} na pasku",
                initial=module['key'] in nav_modules,
                widget=forms.CheckboxInput(attrs={'class': 'checkbox-input'}),
            )
        for stat in DASHBOARD_STAT_DEFINITIONS:
            self.fields[f"stat_{stat['key']}"] = forms.BooleanField(
                required=False,
                label=stat['title'],
                initial=stat['key'] in dashboard_stats,
                widget=forms.CheckboxInput(attrs={'class': 'checkbox-input'}),
            )
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
        visible_modules = normalize_visible_modules([
            module['key']
            for module in MODULE_DEFINITIONS
            if module['key'] == 'settings' or self.cleaned_data.get(f"show_{module['key']}")
        ])
        settings.visible_modules = visible_modules
        settings.nav_modules = normalize_nav_modules(
            [
                module['key']
                for module in MODULE_DEFINITIONS
                if module['key'] != 'settings' and self.cleaned_data.get(f"nav_{module['key']}")
            ],
            visible_keys=visible_modules,
        )
        settings.dashboard_stats = normalize_dashboard_stats(
            [
                stat['key']
                for stat in DASHBOARD_STAT_DEFINITIONS
                if self.cleaned_data.get(f"stat_{stat['key']}")
            ],
            visible_keys=visible_modules,
        )
        if commit:
            settings.save()
        return settings

class UserBackupImportForm(forms.Form):
    backup_file = forms.FileField(
        label='Plik kopii danych',
        help_text='Wybierz plik ZIP lub JSON utworzony przez eksport danych gospodarstwa.',
        widget=forms.FileInput(attrs={'accept': '.zip,.json'}),
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['backup_file'].widget.attrs['class'] = 'form-control'


class UserBackupApplyForm(forms.Form):
    MODES = (
        ('ADD_MISSING', 'Dodaj tylko brakujące dane'),
        ('REPLACE_FARM', 'Zastąp dane gospodarstwa'),
    )
    preview_token = forms.CharField(widget=forms.HiddenInput)
    import_mode = forms.ChoiceField(label='Sposób importu', choices=MODES, widget=forms.RadioSelect)
    confirmation = forms.CharField(label='Potwierdzenie', required=False)
    confirm_replace = forms.BooleanField(label='Rozumiem, że obecne dane gospodarstwa zostaną usunięte.', required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('import_mode') == 'REPLACE_FARM':
            if not cleaned.get('confirm_replace'):
                self.add_error('confirm_replace', 'Potwierdzenie jest wymagane.')
            if cleaned.get('confirmation', '').strip() != 'ZASTĄP DANE GOSPODARSTWA':
                self.add_error('confirmation', 'Wpisz dokładnie: ZASTĄP DANE GOSPODARSTWA')
        return cleaned


class CsvImportForm(forms.Form):
    csv_archive = forms.FileField(
        label="Archiwum CSV (ZIP)",
        widget=forms.FileInput(attrs={"accept": ".zip", "class": "form-control"}),
    )
    confirm_empty_import = forms.BooleanField(
        label="Potwierdzam import do pustego gospodarstwa.",
        widget=forms.CheckboxInput(attrs={"class": "checkbox-input"}),
    )

class ModulePinForm(forms.Form):
    module_key = forms.ChoiceField(
        choices=[
            (module["key"], module["title"])
            for module in MODULE_DEFINITIONS
            if module["key"] != "settings"
        ],
        widget=forms.HiddenInput,
    )
    is_pinned = forms.BooleanField(
        required=False,
        widget=forms.HiddenInput,
    )
