# sows/forms.py
from django import forms
from .models import SowModel, SowEventModel


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
    technician = forms.CharField(label="Inseminator / Technik", required=False)
    born_alive = forms.IntegerField(label="Urodzone żywe", min_value=0, required=False)
    born_dead = forms.IntegerField(label="Urodzone martwe", min_value=0, required=False)
    count = forms.IntegerField(label="Liczba odsadzonych prosiąt", min_value=0, required=False)

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

    def save(self, commit=True):
        instance = super().save(commit=False)
        event_type = self.cleaned_data.get('event_type')
        details = {}

        if event_type == 'INSEMINATION':
            details['technician'] = self.cleaned_data.get('technician') or ""
        elif event_type == 'FARROWING':
            details['born_alive'] = self.cleaned_data.get('born_alive') or 0
            details['born_dead'] = self.cleaned_data.get('born_dead') or 0
        elif event_type == 'WEANING':
            details['count'] = self.cleaned_data.get('count') or 0

        instance.details = details
        if commit:
            instance.save()
        return instance