from django.conf import settings
from django.db import models

from farms.dashboard_registry import default_dashboard_stats
from farms.defaults import (
    DEFAULT_PRODUCTION_QUANTITY_KG,
    FARROWING_ALERT_DAYS_AHEAD,
    GESTATION_DAYS,
    PREGNANCY_CHECK_AFTER_DAYS,
)
from farms.module_registry import default_nav_modules, default_visible_modules


class FarmModel(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='farm')
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gospodarstwo"
        verbose_name_plural = "Gospodarstwa"

    def __str__(self):
        return self.name


class FarmSettingsModel(models.Model):
    INTERFACE_SCALE_CHOICES = [
        ("compact", "Kompaktowy"),
        ("comfortable", "Wygodny"),
        ("large", "Powiększony"),
    ]

    farm = models.OneToOneField(
        "farms.FarmModel",
        on_delete=models.CASCADE,
        related_name="settings",
    )
    pregnancy_check_after_days = models.PositiveIntegerField(default=PREGNANCY_CHECK_AFTER_DAYS)
    gestation_days = models.PositiveIntegerField(default=GESTATION_DAYS)
    farrowing_alert_days_ahead = models.PositiveIntegerField(default=FARROWING_ALERT_DAYS_AHEAD)
    vaccination_alert_days_ahead = models.PositiveIntegerField(default=7)
    allow_farrowing_without_pregnancy_check = models.BooleanField(default=True)
    ask_before_auto_pregnancy_check = models.BooleanField(default=True)
    default_production_quantity_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=DEFAULT_PRODUCTION_QUANTITY_KG,
    )
    default_dashboard_period = models.CharField(max_length=20, default="6m")
    date_format = models.CharField(max_length=20, default="YYYY-MM-DD")
    visible_modules = models.JSONField(default=default_visible_modules, blank=True)
    nav_modules = models.JSONField(default=default_nav_modules, blank=True)
    dashboard_stats = models.JSONField(default=default_dashboard_stats, blank=True)
    interface_scale = models.CharField(
        max_length=16,
        choices=INTERFACE_SCALE_CHOICES,
        default="compact",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ustawienia gospodarstwa"
        verbose_name_plural = "Ustawienia gospodarstw"

    def __str__(self):
        return f"Ustawienia: {self.farm.name}"


class AuditLogModel(models.Model):
    farm = models.ForeignKey(
        FarmModel,
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="farm_audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=50)
    model_label = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("farm", "-created_at"), name="audit_farm_created_idx"),
        ]
        verbose_name = "Wpis historii zmian"
        verbose_name_plural = "Historia zmian"

    def __str__(self):
        return f"{self.action}: {self.object_repr or self.model_label}"
