# sows/models.py

from django.db import models
from datetime import date


class VaccinationPlanModel(models.Model):
    """Słownik planowanych szczepień dla całego stada."""
    name = models.CharField(max_length=100, verbose_name="Nazwa szczepienia")
    days_before_farrowing = models.IntegerField(null=True, blank=True, help_text="Ile dni przed porodem?")
    interval_months = models.IntegerField(null=True, blank=True, help_text="Cyklicznie co X miesięcy?")

    def __str__(self):
        return self.name

class SowModel(models.Model):
    ear_tag = models.CharField(max_length=50)
    entry_date = models.DateField(default=date.today) # Domyślnie dzisiejsza data
    created_at = models.DateTimeField(auto_now_add=True) # Automatyczna data utworzenia

    def __str__(self):
        return f"Maciora {self.ear_tag}"

class SowEventModel(models.Model):
    EVENT_TYPES = [
        ('INSEMINATION', 'Inseminacja'),
        ('PREGNANCY_CHECK', 'Badanie'),
        ('FARROWING', 'Oproszenie'),
        ('WEANING', 'Odsadzenie'),
        ('VACCINATION', 'Szczepienie'),
    ]

    sow = models.ForeignKey(SowModel, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    event_date = models.DateField()
    details = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.event_type} - {self.event_date} (Maciora: {self.sow.ear_tag})"