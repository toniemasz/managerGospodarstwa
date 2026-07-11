# sows/models.py

from datetime import date

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


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
    ARCHIVE_REASON_MANUAL = 'manual'
    ARCHIVE_REASON_DEATH = 'death'
    ARCHIVE_REASON_CHOICES = [
        (ARCHIVE_REASON_MANUAL, 'Ręczna archiwizacja'),
        (ARCHIVE_REASON_DEATH, 'Upadek'),
    ]

    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='sows',
        verbose_name="Gospodarstwo",
    )
    ear_tag = models.CharField(max_length=50)
    entry_date = models.DateField(default=date.today) # Domyślnie dzisiejsza data
    created_at = models.DateTimeField(auto_now_add=True) # Automatyczna data utworzenia
    is_archived = models.BooleanField(default=False, verbose_name="Czy zarchiwizowana?")
    archived_at = models.DateTimeField(null=True, blank=True)
    archive_reason = models.CharField(
        max_length=20,
        choices=ARCHIVE_REASON_CHOICES,
        default=ARCHIVE_REASON_MANUAL,
        verbose_name="Powód archiwizacji",
    )
    death_date = models.DateField(null=True, blank=True, verbose_name="Data upadku")
    death_note = models.TextField(blank=True, verbose_name="Notatka o upadku")

    def __str__(self):
        return f"Maciora {self.ear_tag}"

class SowEventModel(models.Model):
    EVENT_TYPES = [
        ('INSEMINATION', 'Inseminacja'),
        ('PREGNANCY_CHECK', 'Badanie'),
        ('FARROWING', 'Oproszenie'),
        ('WEANING', 'Odsadzenie'),
        ('MISCARRIAGE', 'Poronienie'),
        ('VACCINATION', 'Szczepienie'),
    ]

    sow = models.ForeignKey(SowModel, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    event_date = models.DateField()
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.event_date} (Maciora: {self.sow.ear_tag})"


class MortalityReportModel(models.Model):
    TYPE_SOW = 'sow'
    TYPE_POST_WEANING = 'post_weaning'
    TYPE_CHOICES = [
        (TYPE_SOW, 'Maciora'),
        (TYPE_POST_WEANING, 'Zwierzęta po odsadzeniu'),
    ]

    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='mortality_reports',
        verbose_name="Gospodarstwo",
    )
    mortality_type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name="Typ upadku",
    )
    sow = models.ForeignKey(
        SowModel,
        on_delete=models.SET_NULL,
        related_name='mortality_reports',
        null=True,
        blank=True,
        verbose_name="Maciora",
    )
    mortality_date = models.DateField(verbose_name="Data upadku")
    quantity = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name="Liczba sztuk",
    )
    reason = models.CharField(max_length=200, blank=True, verbose_name="Przyczyna")
    note = models.TextField(blank=True, verbose_name="Notatka")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='sow_mortality_reports',
        null=True,
        blank=True,
        verbose_name="Utworzył",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Utworzono")

    class Meta:
        ordering = ('-mortality_date', '-created_at', '-id')
        indexes = [
            models.Index(fields=('farm', '-mortality_date'), name='mortality_farm_date_idx'),
        ]
        verbose_name = "Zgłoszenie upadku"
        verbose_name_plural = "Zgłoszenia upadków"

    def __str__(self):
        return f"{self.get_mortality_type_display()} - {self.mortality_date}"
