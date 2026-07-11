from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class CostCategoryModel(models.Model):
    farm = models.ForeignKey(
        "farms.FarmModel",
        on_delete=models.CASCADE,
        related_name="cost_categories",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("farm", "name"),
                name="unique_cost_category_name_per_farm",
            ),
        ]
        verbose_name = "Kategoria kosztu"
        verbose_name_plural = "Kategorie kosztów"

    def __str__(self):
        return self.name


class CostModel(models.Model):
    farm = models.ForeignKey(
        "farms.FarmModel",
        on_delete=models.CASCADE,
        related_name="costs",
    )
    category = models.ForeignKey(
        CostCategoryModel,
        on_delete=models.PROTECT,
        related_name="costs",
        null=True,
        blank=True,
    )
    date = models.DateField(verbose_name="Data kosztu")
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name="Kwota",
    )
    description = models.TextField(verbose_name="Opis")
    document_number = models.CharField(max_length=100, blank=True, verbose_name="Numer dokumentu")
    supplier = models.CharField(max_length=200, blank=True, verbose_name="Dostawca")
    is_paid = models.BooleanField(default=False, verbose_name="Opłacony")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_costs",
        null=True,
        blank=True,
    )
    production = models.OneToOneField(
        "feed.ProductionModel",
        on_delete=models.CASCADE,
        related_name="cost_entry",
        null=True,
        blank=True,
        verbose_name="Śrutowanie źródłowe",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-date", "-id")
        indexes = [
            models.Index(fields=("farm", "date"), name="cost_farm_date_idx"),
            models.Index(fields=("farm", "is_paid"), name="cost_farm_paid_idx"),
        ]
        verbose_name = "Koszt"
        verbose_name_plural = "Koszty"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.category_id and self.category.farm_id != self.farm_id:
            raise ValidationError({"category": "Kategoria nie należy do tego gospodarstwa."})
        if self.production_id and self.production.recipe.farm_id != self.farm_id:
            raise ValidationError({"production": "Śrutowanie nie należy do tego gospodarstwa."})

    def __str__(self):
        return f"{self.date}: {self.description} ({self.amount} zł)"
