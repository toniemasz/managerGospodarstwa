from django.db import models
from django.db.models.functions import ExtractYear, Lower, Trim
from decimal import Decimal
from django.utils import timezone

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

    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='pig_sales',
        verbose_name="Gospodarstwo",
    )
    sale_date = models.DateField(default=timezone.localdate, blank=True, null=True, verbose_name="Data sprzedaży")
    document_number = models.CharField(max_length=50, blank=True, verbose_name="Numer dokumentu")
    tattoo = models.CharField(max_length=50, blank=True, verbose_name="Tatuaż")
    no_settlement = models.BooleanField(default=False, verbose_name="Bez rozliczenia")
    settlement_review_required = models.BooleanField(
        default=False,
        verbose_name="Import wymaga sprawdzenia",
    )

    quantity = models.PositiveIntegerField(default=0, verbose_name="Ilość sprzedanych sztuk")
    total_weight = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'), verbose_name="Waga całkowita (kg)")
    meat_class = models.CharField(max_length=10, choices=CLASS_CHOICES, default='INNA', verbose_name="Klasa mięsności")
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'), verbose_name="Cena za kg (PLN)")
    avg_meatiness_seurop = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Średnia mięsność SEUROP (%)")
    live_weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Waga żywa (kg)")
    dressing_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Wybój (%)")
    net_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Wartość netto")
    vat_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="VAT")
    gross_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Wartość brutto")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sale_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                models.F('farm'),
                ExtractYear('sale_date'),
                Lower(Trim('document_number')),
                condition=models.Q(document_number__gt='', sale_date__isnull=False),
                name='unique_sale_document_per_farm_year_ci',
            ),
        ]

    def __str__(self):
        sale_date = self.sale_date or "bez daty"
        return f"Sprzedaż {self.quantity} szt. - {sale_date}"

    @property
    def settlement_status(self) -> str:
        if self.no_settlement:
            return "Brak rozliczenia"
        if self.settlement_review_required:
            return "Import wymaga sprawdzenia"
        return "Kompletne rozliczenie"

    @property
    def total_price(self) -> Decimal:
        if self.gross_value:
            return self.gross_value
        return self.total_weight * self.price_per_kg

    def recalculate_from_rows(self) -> None:
        rows = list(self.rows.all())
        if not rows:
            self.quantity = 0
            self.total_weight = Decimal('0.00')
            self.price_per_kg = Decimal('0.00')
            self.net_value = Decimal('0.00')
            self.vat_value = Decimal('0.00')
            self.gross_value = Decimal('0.00')
            return

        self.quantity = sum((row.quantity or 0) for row in rows)
        self.total_weight = sum((row.weight or Decimal('0.00')) for row in rows)
        self.net_value = sum((row.net_value or Decimal('0.00')) for row in rows)
        self.vat_value = sum((row.vat_value or Decimal('0.00')) for row in rows)
        self.gross_value = sum((row.gross_value or Decimal('0.00')) for row in rows)

        weighted_price = Decimal('0.00')
        priced_weight = Decimal('0.00')
        for row in rows:
            if row.weight and row.price_per_kg is not None:
                weighted_price += row.weight * row.price_per_kg
                priced_weight += row.weight
        if priced_weight:
            self.price_per_kg = weighted_price / priced_weight


class SaleClassRowModel(models.Model):
    sale = models.ForeignKey(PigSaleModel, on_delete=models.CASCADE, related_name='rows')
    line_no = models.PositiveIntegerField(verbose_name="Lp")
    meat_class = models.CharField(max_length=20, blank=True, verbose_name="Klasa")
    quantity = models.PositiveIntegerField(blank=True, null=True, verbose_name="Ilość")
    weight = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Waga")
    avg_weight = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, verbose_name="Średnia waga")
    avg_meatiness = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True, verbose_name="Średnia mięsność")
    price_per_kg = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, verbose_name="Cena")
    net_value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="Wartość")
    vat_value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="VAT")
    gross_value = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, verbose_name="Wartość brutto")

    class Meta:
        ordering = ['line_no', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=('sale', 'line_no'),
                name='unique_sale_line_number',
            ),
        ]
        verbose_name = "Wiersz klasy sprzedaży"
        verbose_name_plural = "Wiersze klas sprzedaży"

    def __str__(self):
        return f"{self.line_no}. {self.meat_class or '-'}"
