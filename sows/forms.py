# sows/forms.py
from django import forms
from .models import SowModel, SowEventModel
from django.core.exceptions import ValidationError


class SowForm(forms.ModelForm):
    class Meta:
        model = SowModel
        fields = ['ear_tag', 'entry_date']
        labels = {
            'ear_tag': 'Numer Kolczyka',
            'entry_date': 'Data wprowadzenia do stada',
        }
        widgets = {
            'entry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class SowEventForm(forms.ModelForm):
    # Dotychczasowe pola dodatkowe
    technician = forms.CharField(label="Inseminator / Technik", required=False)
    born_alive = forms.IntegerField(label="Urodzone żywe", min_value=0, required=False)
    born_dead = forms.IntegerField(label="Urodzone martwe", min_value=0, required=False)
    count = forms.IntegerField(label="Liczba odsadzonych prosiąt", min_value=0, required=False)

    # Nowe pola dla badania USG oraz szczepień
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
    vaccine_name = forms.CharField(label="Nazwa szczepienia / Szczepionka", max_length=100, required=False)

    class Meta:
        model = SowEventModel
        fields = ['event_type', 'event_date']
        labels = {
            'event_type': 'Typ zdarzenia',
            'event_date': 'Data zdarzenia',
        }
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.sow_status = kwargs.pop('sow_status', None)
        super().__init__(*args, **kwargs)

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

            # Szczepienia ochronne są dozwolone w każdym momencie cyklu
            if event_type == 'VACCINATION':
                return cleaned_data

            # Mapowanie stanów i dozwolonych typów zdarzeń
            state_validation = {
                'LACTATING': {
                    'allowed': ['WEANING'],
                    'message': "Błąd: Maciora jest w okresie laktacji (karmiąca). Następnym krokiem w cyklu musi być 'Odsadzenie'!"
                },
                'IDLE': {
                    'allowed': ['INSEMINATION'],
                    'message': "Błąd: Maciora jest jałowa. Rozpocznij nowy cykl produkcyjny wybierając 'Inseminacja'."
                },
                'INSEMINATED': {
                    'allowed': ['PREGNANCY_CHECK', 'INSEMINATION'],
                    'message': "Błąd: Maciora jest po inseminacji. Następnym krokiem powinno być 'Badanie USG' (potwierdzenie ciąży) lub ponowna 'Inseminacja'."
                },
                'TO_RECHECK': {
                    'allowed': ['PREGNANCY_CHECK', 'INSEMINATION'],
                    'message': "Błąd: Status maciory to 'Do rebadania (?)'. Wybierz ponowne 'Badanie USG' lub nową 'Inseminację'."
                },
                'PREGNANT': {
                    'allowed': ['FARROWING', 'INSEMINATION'],
                    'message': "Błąd: Maciora ma potwierdzoną ciążę (Prośna). Naturalnym następnym krokiem jest 'Oproszenie'."
                },
            }

            if self.sow_status in state_validation:
                validation_rule = state_validation[self.sow_status]
                if event_type not in validation_rule['allowed']:
                    self.add_error('event_type', validation_rule['message'])

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
