from django.db import models
from datetime import date
from django.core.validators import MinValueValidator, MaxValueValidator

class IngredientModel(models.Model):
    """Słownik składników (np. Pszenica, Jęczmień, Kukurydza, Soja, Premiks)."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa składnika")
    description = models.TextField(blank=True, null=True, verbose_name="Opis/Uwagi")

    def __str__(self):
        return self.name

class RecipeModel(models.Model):
    """Definicja receptury."""
    name = models.CharField(max_length=100, unique=True, verbose_name="Nazwa receptury")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class RecipeItemModel(models.Model):
    """Składniki wchodzące w skład receptury z określeniem procentowym."""
    recipe = models.ForeignKey(RecipeModel, related_name='items', on_delete=models.CASCADE)
    ingredient = models.ForeignKey(IngredientModel, on_delete=models.PROTECT)
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0.01), MaxValueValidator(100.00)],
        verbose_name="Procent (%)"
    )

    def __str__(self):
        return f"{self.recipe.name} - {self.ingredient.name} ({self.percentage}%)"

class DeliveryModel(models.Model):
    """Dostawa składnika do magazynu."""
    ingredient = models.ForeignKey(IngredientModel, on_delete=models.PROTECT, verbose_name="Składnik")
    date = models.DateField(default=date.today, verbose_name="Data dostawy")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Ilość (kg)")
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Cena za kg (informacyjnie)")

    def __str__(self):
        return f"Dostawa {self.ingredient.name} - {self.quantity_kg} kg"

class ProductionModel(models.Model):
    """Śrutowanie - produkcja paszy na podstawie receptury."""
    recipe = models.ForeignKey(RecipeModel, on_delete=models.PROTECT, verbose_name="Receptura")
    date = models.DateField(default=date.today, verbose_name="Data śrutowania")
    quantity_kg = models.DecimalField(max_digits=10, decimal_places=2, default=2000.00, verbose_name="Ilość (kg)")

    def __str__(self):
        return f"Śrutowanie {self.recipe.name} - {self.quantity_kg} kg"

class IngredientPriceConfigModel(models.Model):
    """Konfiguracja cen składników do kalkulatora kosztów."""
    ingredient = models.OneToOneField(IngredientModel, on_delete=models.CASCADE, related_name='price_config')
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=4, default=0.0000, verbose_name="Cena za kg do kalkulatora")

    def __str__(self):
        return f"Cena {self.ingredient.name}: {self.price_per_kg} PLN/kg"