# sows/forms.py
from django import forms

from .infrastructure.repositories import VaccinationPlanRepository
from .models import SowModel, SowEventModel, VaccinationPlanModel
from django.core.exceptions import ValidationError


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
            'entry_date': forms.DateInput(attrs={'type': 'date'}),
        }


class SowEventForm(forms.ModelForm):
    # Dotychczasowe pola dodatkowe

    vaccine_name = forms.ChoiceField(label="Nazwa szczepienia / Szczepionka", required=False)
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


        repo = VaccinationPlanRepository()
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

            # Szczepienia ochronne są dozwolone w każdym momencie cyklu
            if event_type == 'VACCINATION':
                return cleaned_data

            if self.sow_status == 'LACTATING' and event_type != 'WEANING':
                self.add_error('event_type',
                               "Błąd: Maciora jest w okresie laktacji (karmiąca). Następnym krokiem w cyklu musi być 'Odsadzenie'!")

            elif self.sow_status == 'IDLE' and event_type != 'INSEMINATION':
                self.add_error('event_type',
                               "Błąd: Maciora jest jałowa. Rozpocznij nowy cykl produkcyjny wybierając 'Inseminacja'.")

            elif self.sow_status == 'INSEMINATED' and event_type not in ['PREGNANCY_CHECK', 'INSEMINATION']:
                self.add_error('event_type',
                               "Błąd: Maciora jest po inseminacji. Następnym krokiem powinno być 'Badanie USG' (potwierdzenie ciąży) lub ponowna 'Inseminacja'.")

            elif self.sow_status == 'TO_RECHECK' and event_type not in ['PREGNANCY_CHECK', 'INSEMINATION']:
                self.add_error('event_type',
                               "Błąd: Status maciory to 'Do rebadania (?)'. Wybierz ponowne 'Badanie USG' lub nową 'Inseminację'.")

            elif self.sow_status == 'PREGNANT' and event_type not in ['FARROWING', 'INSEMINATION']:
                self.add_error('event_type',
                               "Błąd: Maciora ma potwierdzoną ciążę (Prośna). Naturalnym następnym krokiem jest 'Oproszenie'.")
            elif self.sow_status in ['INSEMINATED', 'TO_CHECK', 'TO_RECHECK'] and event_type not in ['PREGNANCY_CHECK',
                                                                                                     'INSEMINATION']:
                self.add_error('event_type',
                               "Błąd: Maciora oczekuje na weryfikację ciąży. Następnym krokiem powinno być 'Badanie USG' lub ponowna 'Inseminacja'.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        event_type = self.cleaned_data.get('event_type')
        details = {}

        # Mapowanie danych dynamicznych do pola JSONB na podstawie typu zdarzenia
        if event_type == 'INSEMINATION':
            details['technician'] = self.cleaned_data.get('technician') or ""
        elif event_type == 'PREGNANCY_CHECK':
            details['result'] = self.cleaned_data.get('pregnancy_result') or ""
        elif event_type == 'FARROWING':
            details['born_alive'] = self.cleaned_data.get('born_alive') or 0
            details['born_dead'] = self.cleaned_data.get('born_dead') or 0
        elif event_type == 'WEANING':
            details['count'] = self.cleaned_data.get('count') or 0
        elif event_type == 'VACCINATION':
            details['vaccine_name'] = self.cleaned_data.get('vaccine_name') or ""

        instance.details = details
        if commit:
            instance.save()
        return instance