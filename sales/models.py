from django.db import models
from datetime import date

class PigSaleModel(models.Model):
    CLASS_CHOICES = [
        ('S', 'Klasa S'),
        ('E', 'Klasa E'),
        ('U', 'Klasa U'),
        ('R', 'Klasa R'),
        ('O', 'Klasa O'),
        ('P', 'Klasa P'),
        ('INNA', 'Inna klasa'),
    ]

    sale_date = models.DateField(default=date.today, verbose_name="Data sprzedaży")
    quantity = models.PositiveIntegerField(verbose_name="Ilość sprzedanych sztuk")
    total_weight = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Waga całkowita (kg)")
    meat_class = models.CharField(max_length=10, choices=CLASS_CHOICES, default='INNA', verbose_name="Klasa mięsności")
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Cena za kg (PLN)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sale_date', '-created_at']

    def __str__(self):
        return f"Sprzedaż {self.quantity} szt. - {self.sale_date}"
