# sows/forms.py
from django import forms
from django.utils import timezone
from django.forms import formset_factory

from .services.sow_repository import VaccinationPlanRepository
from .models import MortalityReportModel, SowModel, SowEventModel, VaccinationPlanModel
from django.core.exceptions import ValidationError
from sows.domain.event_details import build_event_details
from sows.domain.sow_state_machine import SowStateMachine


class VaccinationPlanForm(forms.ModelForm):
    TRIGGER_INTERVAL = "INTERVAL"
    TRIGGER_BEFORE_FARROWING = "BEFORE_FARROWING"
    TRIGGER_AFTER_EVENT = "AFTER_EVENT"

    TRIGGER_TYPE_CHOICES = [
        ("", "Wybierz sposób wyznaczania terminu"),
        (TRIGGER_INTERVAL, "Cyklicznie co określony czas"),
        (TRIGGER_BEFORE_FARROWING, "Przed oproszeniem"),
        (TRIGGER_AFTER_EVENT, "Po zdarzeniu"),
    ]

    trigger_type = forms.ChoiceField(
        label="Sposób wyznaczania terminu",
        choices=TRIGGER_TYPE_CHOICES,
        required=True,
    )

    reinclude_sows = forms.ModelMultipleChoiceField(
        queryset=SowModel.objects.none(),
        required=False,
        label="Ponownie obejmij wykluczone maciory",
        help_text="Wybrane maciory wrócą do planu po zapisaniu zmian.",
    )

    class Meta:
        model = VaccinationPlanModel
        fields = [
            'name',
            'trigger_type',
            'days_before_farrowing',
            'days_after_event',
            'event_source',
            'interval_value',
            'interval_unit',
            'schedule_mode',
            'first_due_date',
            'scope',
            'selected_sows',
            'reminder_days_ahead',
        ]
        labels = {
            'name': 'Nazwa szczepienia',
            'days_before_farrowing': 'Dni przed porodem',
            'days_after_event': 'Dni po zdarzeniu',
            'event_source': 'Typ zdarzenia (jeśli po zdarzeniu)',
            'interval_value': 'Interwał',
            'interval_unit': 'Jednostka interwału',
            'schedule_mode': 'Tryb harmonogramu',
            'first_due_date': 'Data pierwszego terminu',
            'scope': 'Zakres planu',
            'selected_sows': 'Wybrane aktywne maciory',
            'reminder_days_ahead': 'Wyprzedzenie przypomnienia (dni)'
        }
        widgets = {
            'first_due_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'selected_sows': forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        self.fields['scope'].required = False
        self.fields['scope'].initial = VaccinationPlanModel.SCOPE_ALL
        if self.farm is not None:
            self.instance.farm = self.farm
            active_sows = SowModel.objects.filter(farm=self.farm, is_archived=False).order_by('ear_tag')
            self.fields['selected_sows'].queryset = active_sows
            if self.instance.pk:
                self.fields['reinclude_sows'].queryset = self.instance.excluded_sows.filter(
                    farm=self.farm,
                    is_archived=False,
                ).order_by('ear_tag')
                if not self.is_bound:
                    self.initial['trigger_type'] = self._detect_trigger_type()

                    if (
                            self.instance.pk
                            and self.instance.interval_value is None
                            and self.instance.interval_months is not None
                    ):
                        self.initial['interval_value'] = self.instance.interval_months
                        self.initial['interval_unit'] = VaccinationPlanModel.INTERVAL_MONTHS

    def _detect_trigger_type(self) -> str:
        """Rozpoznaje typ harmonogramu istniejącego planu."""

        detected_types = []

        if self.instance.days_before_farrowing is not None:
            detected_types.append(self.TRIGGER_BEFORE_FARROWING)

        if self.instance.days_after_event is not None:
            detected_types.append(self.TRIGGER_AFTER_EVENT)

        if (
                self.instance.interval_value is not None
                or self.instance.interval_months is not None
        ):
            detected_types.append(self.TRIGGER_INTERVAL)

        if len(detected_types) == 1:
            return detected_types[0]

        return ""

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.farm is not None:
            exists = VaccinationPlanModel.objects.filter(farm=self.farm, name__iexact=name).exclude(pk=self.instance.pk).exists()
            if exists:
                raise ValidationError("Taki plan szczepienia istnieje już w tym gospodarstwie.")
        return name

    def clean(self):
        cleaned_data = super().clean()

        trigger_type = cleaned_data.get('trigger_type')
        cleaned_data['scope'] = (
                cleaned_data.get('scope')
                or VaccinationPlanModel.SCOPE_ALL
        )

        if trigger_type == self.TRIGGER_BEFORE_FARROWING:
            if cleaned_data.get('days_before_farrowing') is None:
                self.add_error(
                    'days_before_farrowing',
                    "Podaj, ile dni przed oproszeniem ma przypadać szczepienie.",
                )

            cleaned_data['days_after_event'] = None
            cleaned_data['event_source'] = None
            cleaned_data['interval_value'] = None
            cleaned_data['interval_unit'] = None
            cleaned_data['schedule_mode'] = None
            cleaned_data['first_due_date'] = None

        elif trigger_type == self.TRIGGER_AFTER_EVENT:
            if cleaned_data.get('days_after_event') is None:
                self.add_error(
                    'days_after_event',
                    "Podaj, ile dni po zdarzeniu ma przypadać szczepienie.",
                )

            if not cleaned_data.get('event_source'):
                self.add_error(
                    'event_source',
                    "Wybierz zdarzenie, od którego ma być liczony termin.",
                )

            cleaned_data['days_before_farrowing'] = None
            cleaned_data['interval_value'] = None
            cleaned_data['interval_unit'] = None
            cleaned_data['schedule_mode'] = None
            cleaned_data['first_due_date'] = None

        elif trigger_type == self.TRIGGER_INTERVAL:
            required_interval_fields = (
                ('interval_value', "Podaj wartość interwału."),
                ('interval_unit', "Wybierz jednostkę interwału."),
                ('schedule_mode', "Wybierz tryb harmonogramu."),
                ('first_due_date', "Podaj datę pierwszego terminu."),
            )

            for field_name, error_message in required_interval_fields:
                if cleaned_data.get(field_name) in (None, ''):
                    self.add_error(field_name, error_message)

            cleaned_data['days_before_farrowing'] = None
            cleaned_data['days_after_event'] = None
            cleaned_data['event_source'] = None

        scope = cleaned_data.get('scope')

        if scope == VaccinationPlanModel.SCOPE_SELECTED:
            if not cleaned_data.get('selected_sows'):
                self.add_error(
                    'selected_sows',
                    "Wybierz co najmniej jedną aktywną maciorę.",
                )
        else:
            cleaned_data['selected_sows'] = (
                self.fields['selected_sows'].queryset.none()
            )

        reminder_days = cleaned_data.get('reminder_days_ahead')
        if reminder_days is not None and reminder_days < 0:
            self.add_error(
                'reminder_days_ahead',
                "Wyprzedzenie nie może być ujemne.",
            )

        return cleaned_data

    def save(self, commit=True):
        plan = super().save(commit=False)

        if (
                plan.interval_value is not None
                and plan.interval_unit == VaccinationPlanModel.INTERVAL_MONTHS
        ):
            plan.interval_months = plan.interval_value
        else:
            plan.interval_months = None

        plan.requires_configuration = False
        plan.is_active = True

        if commit:
            plan.save()
            self._save_m2m()

        return plan

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
        if event_type == SowStateMachine.VACCINATION:
            plan = VaccinationPlanRepository(self.farm).get_active_plan_by_name(
                details.get('vaccine_name', '')
            ) if self.farm is not None else None
            instance.vaccination_plan = plan
            instance.vaccine_name = details.get('vaccine_name', '')
        if commit:
            instance.save()
        return instance

    def _build_event_details(self, event_type: str) -> dict:
        """Mapuje dane dynamiczne do pola JSONB na podstawie typu zdarzenia."""
        return build_event_details({**self.cleaned_data, 'event_type': event_type})


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
        details = build_event_details(self.cleaned_data)
        if self.cleaned_data.get('event_type') == SowStateMachine.VACCINATION and self.farm is not None:
            plan = VaccinationPlanRepository(self.farm).get_active_plan_by_name(
                details.get('vaccine_name', '')
            )
            if plan:
                details['vaccination_plan_id'] = plan.id
        return details


BulkSowEventFormSet = formset_factory(BulkSowEventRowForm, extra=0, can_delete=True)


def empty_bulk_event_initials(count: int = 8, *, event_type: str = '', event_date=None) -> list[dict]:
    initial = {'event_date': event_date}
    if event_type:
        initial['event_type'] = event_type
    return [initial.copy() for _ in range(count)]


class MortalityReportForm(forms.ModelForm):
    sow = forms.CharField(
        label="Maciora",
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'list': 'mortality-sow-options',
            'autocomplete': 'off',
            'placeholder': 'Wpisz numer maciory',
        }),
    )
    quantity = forms.IntegerField(label="Liczba sztuk", min_value=1, required=False)

    class Meta:
        model = MortalityReportModel
        fields = ['mortality_type', 'sow', 'quantity', 'mortality_date', 'reason', 'note']
        labels = {
            'mortality_type': 'Typ upadku',
            'sow': 'Maciora',
            'mortality_date': 'Data upadku',
            'reason': 'Przyczyna',
            'note': 'Notatka',
        }
        widgets = {
            'mortality_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, farm=None, **kwargs):
        self.farm = farm
        super().__init__(*args, **kwargs)
        self.sow_suggestions = []
        if self.farm is not None:
            self.sow_suggestions = list(SowModel.objects.filter(
                farm=self.farm,
                is_archived=False,
            ).order_by('ear_tag').values('id', 'ear_tag'))
            self.instance.farm = self.farm
        self.fields['sow'].help_text = "Wpisz numer, np. 12, i wybierz maciorę z podpowiedzi albo wpisz pełny numer."
        self.fields['quantity'].help_text = "Dla maciory system zapisuje 1 sztukę; dla zwierząt po odsadzeniu wpisz liczbę."

    def clean(self):
        cleaned_data = super().clean()
        mortality_type = cleaned_data.get('mortality_type')
        mortality_date = cleaned_data.get('mortality_date')
        sow_value = (cleaned_data.get('sow') or '').strip()
        quantity = cleaned_data.get('quantity')

        if mortality_date and mortality_date > timezone.localdate():
            self.add_error('mortality_date', "Data upadku nie może być z przyszłości.")

        if mortality_type == MortalityReportModel.TYPE_SOW:
            sow = self._find_active_sow(sow_value)
            if sow is None and not self.errors.get('sow'):
                self.add_error('sow', "Wybierz aktywną maciorę.")
            elif self.farm is not None and sow.farm_id != self.farm.id:
                self.add_error('sow', "Wybrana maciora nie należy do bieżącego gospodarstwa.")
            elif sow.is_archived:
                self.add_error('sow', "Nie można zgłosić upadku już zarchiwizowanej maciory.")
            cleaned_data['sow'] = sow
            cleaned_data['quantity'] = 1

        elif mortality_type == MortalityReportModel.TYPE_POST_WEANING:
            if quantity is None:
                self.add_error('quantity', "Podaj liczbę sztuk.")
            cleaned_data['sow'] = None
        else:
            cleaned_data['sow'] = None

        return cleaned_data

    def _find_active_sow(self, sow_value):
        if not sow_value or self.farm is None:
            return None

        queryset = SowModel.objects.filter(farm=self.farm, is_archived=False)
        exact_matches = list(queryset.filter(ear_tag__iexact=sow_value)[:2])
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            self.add_error('sow', "W gospodarstwie jest więcej aktywnych macior o takim numerze.")
            return None

        if sow_value.isdigit():
            return queryset.filter(pk=int(sow_value)).first()

        return None
