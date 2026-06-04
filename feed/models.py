# feed/models.py
from decimal import Decimal
from django.db import models
from django.db.models import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse


class IngredientModel(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa składnika")
    description = models.TextField(blank=True, null=True, verbose_name="Opis")
    is_in_bin = models.BooleanField(default=False, verbose_name="Przechowywane w binie (silosie)")

    def __str__(self):
        storage_type = "BIN" if self.is_in_bin else "WOREK"
        return f"{self.name} [{storage_type}]"

    def get_edit_url(self):
        return reverse('edit_ingredient', kwargs={'pk': self.pk})

    def get_delete_url(self):
        return reverse('delete_ingredient', kwargs={'pk': self.pk})


class DeliveryModel(models.Model):
    date = models.DateField(verbose_name="Data dostawy")
    ingredient = models.ForeignKey(IngredientModel, on_delete=models.RESTRICT, related_name='deliveries',
                                   verbose_name="Składnik")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ilość (kg)")
    price_per_kg = models.DecimalField(max_digits=14, decimal_places=5, verbose_name="Cena za kg", null=True,
                                       blank=True)

    def __str__(self):
        return f"Dostawa: {self.ingredient.name} - {self.quantity_kg}kg ({self.date})"

    def get_edit_url(self):
        return reverse('edit_delivery', kwargs={'pk': self.pk})

    def get_delete_url(self):
        return reverse('delete_delivery', kwargs={'pk': self.pk})


class IngredientPriceConfigModel(models.Model):
    ingredient = models.OneToOneField(IngredientModel, on_delete=models.CASCADE, related_name='price_config',
                                      verbose_name="Składnik")
    price_per_kg = models.DecimalField(max_digits=14, decimal_places=5, verbose_name="Domyślna cena za kg")

    def __str__(self):
        return f"Cena: {self.ingredient.name} - {self.price_per_kg} PLN/kg"


class RecipeModel(models.Model):
    name = models.CharField(max_length=150, unique=True, verbose_name="Nazwa receptury")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    def get_edit_url(self):
        return reverse('edit_recipe', kwargs={'pk': self.pk})

    def get_delete_url(self):
        return reverse('delete_recipe', kwargs={'pk': self.pk})


class RecipeItemModel(models.Model):
    recipe = models.ForeignKey('RecipeModel', on_delete=models.CASCADE, related_name='items', verbose_name="Receptura")
    ingredient = models.ForeignKey('IngredientModel', on_delete=models.RESTRICT, verbose_name="Składnik")
    percentage = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Procentowy udział (%)",
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100.00'))]
    )

    def __str__(self):
        return f"{self.recipe.name} - {self.ingredient.name} ({self.percentage}%)"


class ProductionModel(models.Model):
    class Statuses(models.TextChoices):
        QUEUED = 'QUEUED', 'W kolejce'
        STAGE_1_DONE = 'STAGE_1_DONE', 'Etap 1 zakończony (Biny)'
        COMPLETED = 'COMPLETED', 'Zakończone'

    date = models.DateField(verbose_name="Data zaplanowania/produkcji")
    time = models.TimeField(verbose_name="Godzina (Kolejność)", null=True, blank=True)
    recipe = models.ForeignKey(RecipeModel, on_delete=models.RESTRICT, verbose_name="Bazuje na recepturze")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ilość (kg)")

    custom_recipe_data = JSONField(
        blank=True,
        null=True,
        verbose_name="Jednorazowo zmienione proporcje",
        help_text="Format: {'id_skladnika': procent_udzialu}"
    )

    status = models.CharField(
        max_length=20,
        choices=Statuses.choices,
        default=Statuses.QUEUED,
        verbose_name="Status"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def status_label(self) -> str:
        """Jawne mapowanie klucza statusu na czytelną dla człowieka etykietę."""
        return dict(self.Statuses.choices).get(self.status, self.status)

    def __str__(self):
        return f"Śrutowanie: {self.recipe.name} ({self.quantity_kg}kg) - {self.status_label}"
