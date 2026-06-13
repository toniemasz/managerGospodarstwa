# sows/models.py

from django.db import models
from datetime import date


class VaccinationPlanModel(models.Model):
    """Konfiguracja cyklicznych szczepień dla stada."""
    EVENT_SOURCES = [
        ('FARROWING', 'Oproszenie'),
        ('INSEMINATION', 'Inseminacja'),
    ]

    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='vaccination_plans',
        blank=True,
        null=True,
        verbose_name="Gospodarstwo",
    )
    name = models.CharField(max_length=100, verbose_name="Nazwa szczepienia")
    days_before_farrowing = models.IntegerField(null=True, blank=True, help_text="Ile dni przed porodem?")
    days_after_event = models.IntegerField(null=True, blank=True, help_text="Ile dni po zdarzeniu?")
    event_source = models.CharField(max_length=20, choices=EVENT_SOURCES, null=True, blank=True, help_text="Zdarzenie odniesienia")
    interval_months = models.IntegerField(null=True, blank=True, help_text="Cyklicznie co X miesięcy?")
    reminder_days_ahead = models.IntegerField(default=7, help_text="Ile dni wcześniej wyświetlać przypomnienie?")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['farm', 'name'], name='unique_vaccination_plan_name_per_farm')
        ]

    def __str__(self):
        return self.name

class SowModel(models.Model):
    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='sows',
        blank=True,
        null=True,
        verbose_name="Gospodarstwo",
    )
    ear_tag = models.CharField(max_length=50)
    entry_date = models.DateField(default=date.today) # Domyślnie dzisiejsza data
    created_at = models.DateTimeField(auto_now_add=True) # Automatyczna data utworzenia
    is_archived = models.BooleanField(default=False, verbose_name="Czy zarchiwizowana?")
    archived_at = models.DateTimeField(null=True, blank=True)

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
