# feed/models.py
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.db.models import JSONField, Q
from django.core.validators import MinValueValidator, MaxValueValidator

from feed.domain.rules import LOW_STOCK_THRESHOLD_KG


class IngredientModel(models.Model):
    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='ingredients',
        verbose_name="Gospodarstwo",
    )
    name = models.CharField(max_length=100, verbose_name="Nazwa składnika")
    description = models.TextField(blank=True, null=True, verbose_name="Opis")
    low_stock_threshold_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=LOW_STOCK_THRESHOLD_KG,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Próg niskiego stanu (kg)",
        help_text="Alert pojawi się, gdy stan tego składnika spadnie poniżej tej wartości.",
    )

    is_in_bin = models.BooleanField(default=False, verbose_name="Przechowywane w binie (silosie)")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['farm', 'name'], name='unique_ingredient_name_per_farm')
        ]

    def __str__(self):
        storage_type = "BIN" if self.is_in_bin else "WOREK"
        return f"{self.name} [{storage_type}]"

    def save(self, *args, **kwargs):
        if self.farm_id is None:
            from farms.services.farm_service import get_or_create_legacy_farm
            self.farm = get_or_create_legacy_farm()
        return super().save(*args, **kwargs)


class DeliveryModel(models.Model):
    date = models.DateField(verbose_name="Data dostawy")
    ingredient = models.ForeignKey(IngredientModel, on_delete=models.RESTRICT, related_name='deliveries',
                                   verbose_name="Składnik")
    quantity_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Ilość (kg)",
    )
    price_per_kg = models.DecimalField(max_digits=14, decimal_places=5, verbose_name="Cena za kg", null=True,
                                       blank=True)
    remaining_quantity_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Pozostało do rozliczenia FIFO (kg)",
    )

    def __str__(self):
        return f"Dostawa: {self.ingredient.name} - {self.quantity_kg}kg ({self.date})"


class IngredientPriceConfigModel(models.Model):
    ingredient = models.OneToOneField(IngredientModel, on_delete=models.CASCADE, related_name='price_config',
                                      verbose_name="Składnik")
    price_per_kg = models.DecimalField(max_digits=14, decimal_places=5, verbose_name="Domyślna cena za kg")

    def __str__(self):
        return f"Cena: {self.ingredient.name} - {self.price_per_kg} PLN/kg"


class RecipeModel(models.Model):
    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='recipes',
        verbose_name="Gospodarstwo",
    )
    name = models.CharField(max_length=150, verbose_name="Nazwa receptury")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['farm', 'name'], name='unique_recipe_name_per_farm')
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.farm_id is None:
            from farms.services.farm_service import get_or_create_legacy_farm
            self.farm = get_or_create_legacy_farm()
        return super().save(*args, **kwargs)


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


class RecipeVersionModel(models.Model):
    recipe = models.ForeignKey(
        RecipeModel,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name="Receptura",
    )
    version_number = models.PositiveIntegerField(verbose_name="Numer wersji")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='created_recipe_versions',
        null=True,
        blank=True,
        verbose_name="Utworzona przez",
    )
    valid_from = models.DateTimeField(verbose_name="Obowiązuje od")
    valid_to = models.DateTimeField(null=True, blank=True, verbose_name="Obowiązuje do")
    change_note = models.CharField(max_length=255, blank=True, verbose_name="Opis zmiany")
    is_current = models.BooleanField(default=True, verbose_name="Aktualna wersja")

    class Meta:
        ordering = ('recipe_id', '-version_number')
        constraints = [
            models.UniqueConstraint(
                fields=['recipe', 'version_number'],
                name='unique_recipe_version_number',
            ),
            models.UniqueConstraint(
                fields=['recipe'],
                condition=Q(is_current=True),
                name='unique_current_recipe_version',
            ),
        ]
        indexes = [
            models.Index(fields=('recipe', 'is_current'), name='recipe_version_current_idx'),
        ]
        verbose_name = "Wersja receptury"
        verbose_name_plural = "Wersje receptur"

    def __str__(self):
        return f"{self.recipe.name} v{self.version_number}"


class RecipeVersionItemModel(models.Model):
    recipe_version = models.ForeignKey(
        RecipeVersionModel,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Wersja receptury",
    )
    ingredient = models.ForeignKey('IngredientModel', on_delete=models.RESTRICT, verbose_name="Składnik")
    percentage = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Procentowy udział (%)",
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100.00'))],
    )

    class Meta:
        ordering = ('ingredient__name', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=['recipe_version', 'ingredient'],
                name='unique_ingredient_per_recipe_version',
            ),
        ]
        verbose_name = "Pozycja wersji receptury"
        verbose_name_plural = "Pozycje wersji receptur"

    def __str__(self):
        return f"{self.recipe_version} - {self.ingredient.name} ({self.percentage}%)"


class ProductionModel(models.Model):
    class Statuses(models.TextChoices):
        QUEUED = 'QUEUED', 'W kolejce'
        STAGE_1_DONE = 'STAGE_1_DONE', 'Etap 1 zakończony (Biny)'
        COMPLETED = 'COMPLETED', 'Zakończone'

    date = models.DateField(verbose_name="Data zaplanowania/produkcji")
    time = models.TimeField(verbose_name="Godzina (Kolejność)", null=True, blank=True)
    recipe = models.ForeignKey(RecipeModel, on_delete=models.RESTRICT, verbose_name="Bazuje na recepturze")
    recipe_version = models.ForeignKey(
        RecipeVersionModel,
        on_delete=models.SET_NULL,
        related_name='productions',
        null=True,
        blank=True,
        verbose_name="Wersja receptury",
    )
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
    feed_cost_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Koszt składników paszy",
    )
    feed_cost_per_kg = models.DecimalField(
        max_digits=14,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name="Koszt składników paszy za kg",
    )
    feed_cost_is_partial = models.BooleanField(
        default=False,
        verbose_name="Koszt składników jest częściowy",
    )
    feed_cost_note = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Uwagi do kosztu składników",
    )
    completion_feed_serving_mode = models.CharField(max_length=24, blank=True)

    @property
    def status_label(self) -> str:
        """Jawne mapowanie klucza statusu na czytelną dla człowieka etykietę."""
        return dict(self.Statuses.choices).get(self.status, self.status)

    def __str__(self):
        return f"Śrutowanie: {self.recipe.name} ({self.quantity_kg}kg) - {self.status_label}"


class FeedProductModel(models.Model):
    class SourceTypes(models.TextChoices):
        PURCHASED_READY = "PURCHASED_READY", "Kupiona pasza gotowa"
        PRODUCED = "PRODUCED", "Pasza wytworzona"

    farm = models.ForeignKey('farms.FarmModel', on_delete=models.CASCADE, related_name='feed_products')
    name = models.CharField(max_length=150)
    source_type = models.CharField(max_length=24, choices=SourceTypes.choices)
    recipe = models.ForeignKey(RecipeModel, on_delete=models.RESTRICT, null=True, blank=True, related_name='feed_products')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('farm', 'name'), name='unique_feed_product_name_per_farm')]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.recipe_id and self.recipe.farm_id != self.farm_id:
            raise ValidationError("Receptura produktu nie należy do wskazanego gospodarstwa.")

    def __str__(self):
        return self.name


class ReadyFeedDeliveryModel(models.Model):
    farm = models.ForeignKey('farms.FarmModel', on_delete=models.CASCADE, related_name='ready_feed_deliveries')
    product = models.ForeignKey(FeedProductModel, on_delete=models.RESTRICT, related_name='deliveries')
    date = models.DateField()
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    price_per_kg = models.DecimalField(max_digits=14, decimal_places=5, validators=[MinValueValidator(Decimal('0.00001'))])
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FinishedFeedBatchModel(models.Model):
    farm = models.ForeignKey('farms.FarmModel', on_delete=models.CASCADE, related_name='finished_feed_batches')
    product = models.ForeignKey(FeedProductModel, on_delete=models.RESTRICT, related_name='batches')
    batch_date = models.DateField()
    initial_quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    remaining_quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    cost_per_kg = models.DecimalField(max_digits=14, decimal_places=5)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2)
    cost_is_partial = models.BooleanField(default=False)
    production = models.OneToOneField(ProductionModel, on_delete=models.CASCADE, null=True, blank=True, related_name='finished_feed_batch')
    ready_feed_delivery = models.OneToOneField(ReadyFeedDeliveryModel, on_delete=models.CASCADE, null=True, blank=True, related_name='batch')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(initial_quantity_kg__gt=0), name='finished_batch_initial_positive'),
            models.CheckConstraint(condition=Q(remaining_quantity_kg__gte=0) & Q(remaining_quantity_kg__lte=models.F('initial_quantity_kg')), name='finished_batch_remaining_range'),
            models.CheckConstraint(condition=(Q(production__isnull=False, ready_feed_delivery__isnull=True) | Q(production__isnull=True, ready_feed_delivery__isnull=False)), name='finished_batch_exactly_one_source'),
        ]


class FeedServingModel(models.Model):
    farm = models.ForeignKey('farms.FarmModel', on_delete=models.CASCADE, related_name='feed_servings')
    product = models.ForeignKey(FeedProductModel, on_delete=models.RESTRICT, related_name='servings')
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    note = models.CharField(max_length=255, blank=True)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    is_automatic = models.BooleanField(default=False)
    automatic_for_production = models.OneToOneField(ProductionModel, on_delete=models.CASCADE, null=True, blank=True, related_name='automatic_feed_serving')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FeedServingAllocationModel(models.Model):
    serving = models.ForeignKey(FeedServingModel, on_delete=models.CASCADE, related_name='allocations')
    batch = models.ForeignKey(FinishedFeedBatchModel, on_delete=models.RESTRICT, related_name='serving_allocations')
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_cost = models.DecimalField(max_digits=14, decimal_places=5)
    cost = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('serving', 'batch'), name='unique_serving_batch_allocation')]


class ProductionIngredientUsageModel(models.Model):
    farm = models.ForeignKey(
        'farms.FarmModel',
        on_delete=models.CASCADE,
        related_name='feed_ingredient_usages',
        verbose_name="Gospodarstwo",
    )
    production = models.ForeignKey(
        ProductionModel,
        on_delete=models.CASCADE,
        related_name='ingredient_usages',
        verbose_name="Produkcja paszy",
    )
    ingredient = models.ForeignKey(
        IngredientModel,
        on_delete=models.RESTRICT,
        related_name='production_usages',
        verbose_name="Składnik",
    )
    delivery = models.ForeignKey(
        DeliveryModel,
        on_delete=models.PROTECT,
        related_name='production_usages',
        null=True,
        blank=True,
        verbose_name="Dostawa FIFO",
    )
    quantity_kg = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Zużyta ilość (kg)",
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=5,
        default=Decimal('0.00000'),
        verbose_name="Cena jednostkowa",
    )
    cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Koszt",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('production_id', 'ingredient__name', 'delivery__date', 'delivery_id', 'id')
        constraints = [
            models.UniqueConstraint(
                fields=('production', 'ingredient', 'delivery'),
                name='unique_fifo_usage_per_delivery',
            ),
            models.CheckConstraint(
                condition=Q(quantity_kg__gt=0),
                name='fifo_usage_quantity_positive',
            ),
        ]
        indexes = [
            models.Index(fields=('farm', 'ingredient', 'production'), name='fifo_usage_farm_ing_prod_idx'),
            models.Index(fields=('delivery',), name='fifo_usage_delivery_idx'),
        ]
        verbose_name = "Rozliczenie składnika FIFO"
        verbose_name_plural = "Rozliczenia składników FIFO"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.production_id and self.farm_id != self.production.recipe.farm_id:
            raise ValidationError("Produkcja nie należy do wskazanego gospodarstwa.")
        if self.ingredient_id and self.farm_id != self.ingredient.farm_id:
            raise ValidationError("Składnik nie należy do wskazanego gospodarstwa.")
        if self.delivery_id and self.delivery.ingredient_id != self.ingredient_id:
            raise ValidationError("Dostawa FIFO dotyczy innego składnika.")

    def __str__(self):
        delivery_label = f"z dostawy {self.delivery_id}" if self.delivery_id else "bez przypisanej dostawy"
        return f"{self.production}: {self.ingredient.name} {self.quantity_kg} kg {delivery_label}"


class InventoryMovementModel(models.Model):
    class Types(models.TextChoices):
        DELIVERY = "DELIVERY", "Dostawa"
        PRODUCTION_USAGE = "PRODUCTION_USAGE", "Zużycie w produkcji"
        ADJUSTMENT_POSITIVE = "ADJUSTMENT_POSITIVE", "Korekta dodatnia"
        ADJUSTMENT_NEGATIVE = "ADJUSTMENT_NEGATIVE", "Korekta ujemna"
        REVERSAL = "REVERSAL", "Odwrócenie"

    farm = models.ForeignKey(
        "farms.FarmModel",
        on_delete=models.CASCADE,
        related_name="inventory_movements",
    )
    ingredient = models.ForeignKey(
        IngredientModel,
        on_delete=models.RESTRICT,
        related_name="inventory_movements",
    )
    movement_type = models.CharField(max_length=30, choices=Types.choices)
    quantity_kg = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=14, decimal_places=5, null=True, blank=True)
    source_model = models.CharField(max_length=100, blank=True)
    source_id = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="inventory_movements",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    movement_date = models.DateField()

    class Meta:
        ordering = ("-movement_date", "-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity_kg=0),
                name="inventory_movement_quantity_nonzero",
            ),
            models.UniqueConstraint(
                fields=("farm", "ingredient", "movement_type", "source_model", "source_id"),
                condition=~Q(source_id=""),
                name="unique_inventory_source_movement",
            ),
        ]
        indexes = [
            models.Index(fields=("farm", "ingredient", "movement_date"), name="inventory_farm_ing_date_idx"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.ingredient_id and self.farm_id != self.ingredient.farm_id:
            raise ValidationError("Składnik nie należy do wskazanego gospodarstwa.")

    def __str__(self):
        return f"{self.get_movement_type_display()}: {self.quantity_kg} kg {self.ingredient.name}"
