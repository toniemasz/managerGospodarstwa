# sows/forms.py
from django import forms
from django.forms import formset_factory

from .services.sow_repository import VaccinationPlanRepository
from .models import SowModel, SowEventModel, VaccinationPlanModel
from django.core.exceptions import ValidationError
from sows.domain.sow_state_machine import SowStateMachine


class VaccinationPlanForm(forms.ModelForm):
    class Meta:
        model = VaccinationPlanModel
        fields = ['name', 'days_before_farrowing', 'days_after_event', 'event_source', 'interval_months',
                  'reminder_days_ahead']
        labels = {
            'name': 'Nazwa szczepienia',
            'days_before_farrowing': 'Dni przed porodem',
            'days_after_event': 'Dni po zdarzeniu',
            'event_source': 'Typ zdarzenia (jeśli po zdarzeniu)',
            'interval_months': 'Interwał cykliczny (w miesiącach)',
            'reminder_days_ahead': 'Wyprzedzenie przypomnienia (dni)'
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        if self.farm is not None:
            self.instance.farm = self.farm

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.farm is not None:
            exists = VaccinationPlanModel.objects.filter(farm=self.farm, name__iexact=name).exclude(pk=self.instance.pk).exists()
            if exists:
                raise ValidationError("Taki plan szczepienia istnieje już w tym gospodarstwie.")
        return name

    def clean(self):
        cleaned_data = super().clean()
        dbf = cleaned_data.get('days_before_farrowing')
        dae = cleaned_data.get('days_after_event')
        src = cleaned_data.get('event_source')
        im = cleaned_data.get('interval_months')

        # Walidacja logiki biznesowej: przynajmniej jeden warunek musi być wybrany,
        # i nie mogą się one ze sobą logicznie wykluczać.
        conditions = [bool(dbf), bool(dae), bool(im)]
        if sum(conditions) > 1:
            raise ValidationError(
                "Wybierz tylko jedną metodę wyzwalania szczepienia (albo przed porodem, albo po zdarzeniu, albo cyklicznie).")

        if sum(conditions) == 0:
            raise ValidationError("Musisz zdefiniować przynajmniej jeden warunek uruchomienia szczepienia.")

        if dae and not src:
            self.add_error('event_source', "Podaj, od jakiego zdarzenia mają być liczone dni.")

        return cleaned_data

class SowForm(forms.ModelForm):
    class Meta:
        model = SowModel
        fields = ['ear_tag', 'entry_date']
        labels = {
            'ear_tag': 'Numer Kolczyka',
            'entry_date': 'Data wprowadzenia do stada',
        }
        widgets = {
            'entry_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }


class SowEventForm(forms.ModelForm):

    vaccine_name = forms.ChoiceField(label="Nazwa szczepienia / Szczepionka", required=False)
    technician = forms.CharField(label="Inseminator / Technik", required=False)
    born_alive = forms.IntegerField(label="Urodzone żywe", min_value=0, required=False)
    born_dead = forms.IntegerField(label="Urodzone martwe", min_value=0, required=False)
    count = forms.IntegerField(label="Liczba odsadzonych prosiąt", min_value=0, required=False)

    pregnancy_result = forms.ChoiceField(
        label="Wynik badania USG",
        choices=[
            ('', '--- Wybierz wynik ---'),
            ('TAK', 'Prośna (Potwierdzona ciąża)'),
            ('NIE', 'Jałowa (Brak ciąży)'),
            ('?', 'Do rebadania (?)')
        ],
        required=False
    )

    class Meta:
        model = SowEventModel
        fields = ['event_type', 'event_date']
        labels = {
            'event_type': 'Typ zdarzenia',
            'event_date': 'Data zdarzenia',
        }
        widgets = {
            'event_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.sow_status = kwargs.pop('sow_status', None)
        self.farm = kwargs.pop('farm', None)
        super().__init__(*args, **kwargs)


        repo = VaccinationPlanRepository(farm=self.farm)
        self.fields['vaccine_name'].choices = repo.get_plan_choices()

    def clean(self):
        cleaned_data = super().clean()
        event_type = cleaned_data.get('event_type')

        pregnancy_result = cleaned_data.get('pregnancy_result')
        vaccine_name = cleaned_data.get('vaccine_name')

        # 1. Walidacja obecności pól wymaganych dla konkretnych typów zdarzeń
        if event_type == 'PREGNANCY_CHECK' and not pregnancy_result:
            self.add_error('pregnancy_result', "Dla badania USG musisz określić jego wynik.")

        if event_type == 'VACCINATION' and not vaccine_name:
            self.add_error('vaccine_name', "Dla zdarzenia szczepienia wymagane jest podanie nazwy szczepionki.")

        # 2. Walidacja maszyny stanów cyklu produkcyjnego maciory
        if not self.instance.pk and self.sow_status and event_type:
            needs_confirmation = SowStateMachine.requires_confirmation(self.sow_status, event_type)
            if not needs_confirmation and not SowStateMachine.can_add_event(self.sow_status, event_type):
                self.add_error('event_type', SowStateMachine.get_error_message(self.sow_status))

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        event_type = self.cleaned_data.get('event_type')
        details = self._build_event_details(event_type)

        instance.details = details
        if commit:
            instance.save()
        return instance

    def _build_event_details(self, event_type: str) -> dict:
        """Mapuje dane dynamiczne do pola JSONB na podstawie typu zdarzenia."""
        details_mapping = {
            'INSEMINATION': {'technician': self.cleaned_data.get('technician') or ""},
            'PREGNANCY_CHECK': {'result': self.cleaned_data.get('pregnancy_result') or ""},
            'FARROWING': {
                'born_alive': self.cleaned_data.get('born_alive') or 0,
                'born_dead': self.cleaned_data.get('born_dead') or 0
            },
            'WEANING': {'count': self.cleaned_data.get('count') or 0},
            'VACCINATION': {'vaccine_name': self.cleaned_data.get('vaccine_name') or ""},
        }
        return details_mapping.get(event_type, {})


class BulkSowEventRowForm(forms.Form):
    sow_ear_tag = forms.CharField(label="Maciora", required=False, max_length=50)
    event_type = forms.ChoiceField(label="Typ zdarzenia", choices=[('', '---')] + SowEventModel.EVENT_TYPES, required=False)
    event_date = forms.DateField(label="Data", required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}))
    technician = forms.CharField(label="Inseminator", required=False)
    pregnancy_result = forms.ChoiceField(
        label="Wynik USG",
        choices=[
            ('', '---'),
            ('TAK', 'Prośna'),
            ('NIE', 'Jałowa'),
            ('?', 'Do rebadania'),
        ],
        required=False,
    )
    born_alive = forms.IntegerField(label="Żywe", min_value=0, required=False)
    born_dead = forms.IntegerField(label="Martwe", min_value=0, required=False)
    count = forms.IntegerField(label="Odsadzone", min_value=0, required=False)
    vaccine_name = forms.ChoiceField(label="Szczepienie", required=False)

    meaningful_fields = [
        'sow_ear_tag',
        'event_type',
        'event_date',
        'technician',
        'pregnancy_result',
        'born_alive',
        'born_dead',
        'count',
        'vaccine_name',
    ]

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        repo = VaccinationPlanRepository(farm=self.farm)
        self.fields['vaccine_name'].choices = repo.get_plan_choices()
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f'{existing} bulk-event-input'.strip()

    def has_row_data(self) -> bool:
        if hasattr(self, 'cleaned_data'):
            return any(self.cleaned_data.get(field) not in (None, '') for field in self.meaningful_fields)
        return any(self.data.get(self.add_prefix(field)) for field in self.meaningful_fields)

    def clean(self):
        cleaned_data = super().clean()
        if not self.has_row_data():
            return cleaned_data

        required_fields = ['sow_ear_tag', 'event_type', 'event_date']
        for field in required_fields:
            if not cleaned_data.get(field):
                self.add_error(field, "Uzupełnij pole albo zostaw cały wiersz pusty.")

        event_type = cleaned_data.get('event_type')
        if event_type == 'PREGNANCY_CHECK' and not cleaned_data.get('pregnancy_result'):
            self.add_error('pregnancy_result', "Podaj wynik badania.")
        if event_type == 'VACCINATION' and not cleaned_data.get('vaccine_name'):
            self.add_error('vaccine_name', "Wybierz szczepienie.")

        if self.farm and cleaned_data.get('sow_ear_tag'):
            sow = SowModel.objects.filter(
                farm=self.farm,
                ear_tag__iexact=cleaned_data['sow_ear_tag'].strip(),
                is_archived=False,
            ).first()
            if not sow:
                self.add_error('sow_ear_tag', "Nie znaleziono aktywnej maciory o takim numerze.")
            else:
                cleaned_data['sow'] = sow
                if cleaned_data.get('event_date') and cleaned_data['event_date'] < sow.entry_date:
                    self.add_error('event_date', "Data zdarzenia nie może być wcześniejsza niż data wprowadzenia maciory.")

        return cleaned_data

    def build_details(self) -> dict:
        event_type = self.cleaned_data.get('event_type')
        details_mapping = {
            'INSEMINATION': {'technician': self.cleaned_data.get('technician') or ""},
            'PREGNANCY_CHECK': {'result': self.cleaned_data.get('pregnancy_result') or ""},
            'FARROWING': {
                'born_alive': self.cleaned_data.get('born_alive') or 0,
                'born_dead': self.cleaned_data.get('born_dead') or 0,
            },
            'WEANING': {'count': self.cleaned_data.get('count') or 0},
            'VACCINATION': {'vaccine_name': self.cleaned_data.get('vaccine_name') or ""},
        }
        return details_mapping.get(event_type, {})


BulkSowEventFormSet = formset_factory(BulkSowEventRowForm, extra=0, can_delete=True)


def empty_bulk_event_initials(count: int = 8) -> list[dict]:
    return [{'event_date': None} for _ in range(count)]
