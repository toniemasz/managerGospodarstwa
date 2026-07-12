# sows/models.py

from datetime import date

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class VaccinationPlanModel(models.Model):
    """Konfiguracja cyklicznych szczepień dla stada."""
    INTERVAL_DAYS = 'DAYS'
    INTERVAL_WEEKS = 'WEEKS'
    INTERVAL_MONTHS = 'MONTHS'
    INTERVAL_YEARS = 'YEARS'
    INTERVAL_UNIT_CHOICES = [
        (INTERVAL_DAYS, 'dni'),
        (INTERVAL_WEEKS, 'tygodnie'),
        (INTERVAL_MONTHS, 'miesiące'),
        (INTERVAL_YEARS, 'lata'),
    ]

    SCHEDULE_FIXED = 'FIXED'
    SCHEDULE_FROM_LAST_COMPLETED = 'FROM_LAST_COMPLETED'
    SCHEDULE_MODE_CHOICES = [
        (SCHEDULE_FIXED, 'Stały harmonogram'),
        (SCHEDULE_FROM_LAST_COMPLETED, 'Od ostatniego wykonanego szczepienia'),
    ]

    SCOPE_ALL = 'ALL'
    SCOPE_SELECTED = 'SELECTED'
    SCOPE_CHOICES = [
        (SCOPE_ALL, 'Wszystkie aktywne maciory'),
        (SCOPE_SELECTED, 'Wybrane aktywne maciory'),
    ]
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
    interval_value = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="Wartość interwału",
    )
    interval_unit = models.CharField(
        max_length=10,
        choices=INTERVAL_UNIT_CHOICES,
        null=True,
        blank=True,
        verbose_name="Jednostka interwału",
    )
    schedule_mode = models.CharField(
        max_length=24,
        choices=SCHEDULE_MODE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Tryb harmonogramu",
    )
    first_due_date = models.DateField(null=True, blank=True, verbose_name="Data pierwszego terminu")
    scope = models.CharField(
        max_length=10,
        choices=SCOPE_CHOICES,
        default=SCOPE_ALL,
        verbose_name="Zakres planu",
    )
    is_active = models.BooleanField(default=True, verbose_name="Plan aktywny")
    requires_configuration = models.BooleanField(
        default=False,
        verbose_name="Wymaga uzupełnienia konfiguracji",
    )
    selected_sows = models.ManyToManyField(
        'SowModel',
        blank=True,
        related_name='selected_vaccination_plans',
        verbose_name="Wybrane maciory",
    )
    excluded_sows = models.ManyToManyField(
        'SowModel',
        blank=True,
        related_name='excluded_vaccination_plans',
        verbose_name="Wykluczone maciory",
    )
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
    vaccination_plan = models.ForeignKey(
        VaccinationPlanModel,
        on_delete=models.SET_NULL,
        related_name='vaccination_events',
        null=True,
        blank=True,
        verbose_name="Plan szczepienia",
    )
    vaccine_name = models.CharField(max_length=100, blank=True, verbose_name="Nazwa szczepienia")
    cycle_id = models.CharField(max_length=160, blank=True, verbose_name="Identyfikator cyklu")
    scheduled_date = models.DateField(null=True, blank=True, verbose_name="Planowany termin")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_type} - {self.event_date} (Maciora: {self.sow.ear_tag})"


class VaccinationCycleModel(models.Model):
    """Trwały zapis zamkniętego cyklu szczepienia konkretnej maciory."""

    STATUS_COMPLETED = 'COMPLETED'
    STATUS_SKIPPED = 'SKIPPED'
    STATUS_CHOICES = [
        (STATUS_COMPLETED, 'Wykonane'),
        (STATUS_SKIPPED, 'Pominięte'),
    ]

    plan = models.ForeignKey(
        VaccinationPlanModel,
        on_delete=models.PROTECT,
        related_name='cycle_records',
        verbose_name="Plan szczepienia",
    )
    sow = models.ForeignKey(
        SowModel,
        on_delete=models.PROTECT,
        related_name='vaccination_cycles',
        verbose_name="Maciora",
    )
    cycle_id = models.CharField(max_length=160, verbose_name="Identyfikator cyklu")
    scheduled_date = models.DateField(verbose_name="Planowany termin")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES)
    completed_at = models.DateField(null=True, blank=True, verbose_name="Data wykonania")
    skipped_at = models.DateField(null=True, blank=True, verbose_name="Data pominięcia")
    note = models.TextField(blank=True, verbose_name="Powód lub notatka")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('plan', 'sow', 'cycle_id'),
                name='unique_vaccination_cycle_per_sow',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status='COMPLETED',
                        completed_at__isnull=False,
                        skipped_at__isnull=True,
                    )
                    | models.Q(
                        status='SKIPPED',
                        completed_at__isnull=True,
                        skipped_at__isnull=False,
                    )
                ),
                name='vaccination_cycle_status_dates_valid',
            ),
        ]
        indexes = [
            models.Index(
                fields=('plan', 'sow', 'scheduled_date'),
                name='vacc_cycle_plan_sow_date_idx',
            ),
        ]
        ordering = ('scheduled_date', 'id')

    def __str__(self):
        return f"{self.plan} · {self.sow} · {self.scheduled_date}"


class MortalityReportModel(models.Model):
    TYPE_SOW = 'MACIORA'
    TYPE_PIGLET = 'PROSIAK'
    TYPE_WEANER = 'WARCHLAK'
    TYPE_FINISHER = 'TUCZNIK'
    TYPE_UNSPECIFIED_POST_WEANING = 'NIEOKRESLONY_PO_ODSADZENIU'
    TYPE_POST_WEANING = TYPE_UNSPECIFIED_POST_WEANING  # zgodność kodu i importów sprzed migracji
    POST_WEANING_TYPES = (
        TYPE_PIGLET,
        TYPE_WEANER,
        TYPE_FINISHER,
        TYPE_UNSPECIFIED_POST_WEANING,
    )
    TYPE_CHOICES = [
        (TYPE_SOW, 'Maciora'),
        (TYPE_PIGLET, 'Prosiak'),
        (TYPE_WEANER, 'Warchlak'),
        (TYPE_FINISHER, 'Tucznik'),
        (TYPE_UNSPECIFIED_POST_WEANING, 'Nieokreślone po odsadzeniu'),
    ]
    MANUAL_TYPE_CHOICES = TYPE_CHOICES[:4]

    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='mortality_reports',
        verbose_name="Gospodarstwo",
    )
    mortality_type = models.CharField(
        max_length=32,
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
            models.Index(fields=('farm', 'mortality_type', '-mortality_date'), name='mortality_farm_type_date_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(mortality_type__in=(
                    'MACIORA', 'PROSIAK', 'WARCHLAK', 'TUCZNIK',
                    'NIEOKRESLONY_PO_ODSADZENIU',
                )),
                name='mortality_type_valid',
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name='mortality_quantity_positive'),
            models.CheckConstraint(
                condition=(
                    models.Q(mortality_type='MACIORA', sow__isnull=False)
                    | models.Q(
                        mortality_type__in=(
                            'PROSIAK', 'WARCHLAK', 'TUCZNIK',
                            'NIEOKRESLONY_PO_ODSADZENIU',
                        ),
                        sow__isnull=True,
                    )
                ),
                name='mortality_sow_matches_type',
            ),
        ]
        verbose_name = "Zgłoszenie upadku"
        verbose_name_plural = "Zgłoszenia upadków"

    def __str__(self):
        return f"{self.get_mortality_type_display()} - {self.mortality_date}"
