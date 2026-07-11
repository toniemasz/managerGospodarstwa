from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum

from farms.services.cache import invalidate_farm_cache_on_commit
from feed.models import (
    DeliveryModel,
    IngredientModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
)
from feed.calculators.feed_cost import IngredientRequirement, ProductionCalculator
from feed.selectors.recipe_requirements import recipe_item_dicts_for_production
from common.units import format_mass


KG_QUANT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")
PRICE_QUANT = Decimal("0.00001")


class InventoryRebuildError(Exception):
    def __init__(self, message: str, *, farm=None, production: ProductionModel | None = None):
        self.farm = farm
        self.production = production
        super().__init__(message)

    def __str__(self) -> str:
        details = []
        if self.farm is not None:
            details.append(f"farm.id={self.farm.id}")
            details.append(f"farm.name={self.farm.name}")
        if self.production is not None:
            details.append(f"production.id={self.production.id}")
            details.append(f"date={self.production.date}")
            details.append(f"recipe={self.production.recipe.name}")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{super().__str__()}{suffix}"


class InventoryActions:
    def __init__(self, farm):
        self.farm = farm

    def balances(self) -> dict[int, Decimal]:
        queryset = InventoryMovementModel.objects.all()
        if self.farm is not None:
            queryset = queryset.filter(farm=self.farm)
        rows = (
            queryset
            .values("ingredient_id")
            .annotate(total=Sum("quantity_kg"))
        )
        return {row["ingredient_id"]: row["total"] or Decimal("0.00") for row in rows}

    @transaction.atomic
    def sync_delivery(self, delivery: DeliveryModel, *, user=None) -> InventoryMovementModel:
        delivery = DeliveryModel.objects.select_for_update().select_related("ingredient").get(pk=delivery.pk)
        farm = self.farm or delivery.ingredient.farm
        if delivery.ingredient.farm_id != farm.id:
            raise ValidationError("Dostawa nie należy do tego gospodarstwa.")
        movement, _ = InventoryMovementModel.objects.update_or_create(
            farm=farm,
            ingredient=delivery.ingredient,
            movement_type=InventoryMovementModel.Types.DELIVERY,
            source_model=delivery._meta.label,
            source_id=str(delivery.pk),
            defaults={
                "quantity_kg": abs(Decimal(str(delivery.quantity_kg))),
                "unit_price": delivery.price_per_kg,
                "movement_date": delivery.date,
                "created_by": user if getattr(user, "is_authenticated", False) else None,
                "note": "Dostawa magazynowa",
            },
        )
        self.refresh_delivery_remaining(delivery)
        return movement

    @transaction.atomic
    def remove_delivery(self, delivery: DeliveryModel) -> None:
        if ProductionIngredientUsageModel.objects.filter(delivery=delivery).exists():
            raise ValidationError(
                "Nie można usunąć dostawy, która została już rozliczona w produkcji paszy."
            )
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type=InventoryMovementModel.Types.DELIVERY,
            source_model=delivery._meta.label,
            source_id=str(delivery.pk),
        ).delete()

    @staticmethod
    def _quantize_kg(value: Decimal) -> Decimal:
        return Decimal(value).quantize(KG_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _quantize_money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _quantize_price(value: Decimal) -> Decimal:
        return Decimal(value).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def _production_requirements(production: ProductionModel):
        return ProductionCalculator(
            quantity_kg=production.quantity_kg,
            base_recipe_items=recipe_item_dicts_for_production(production),
            custom_recipe_data=production.custom_recipe_data,
        ).get_requirements()

    @staticmethod
    def _movement_requirements(production: ProductionModel, farm):
        movements = InventoryMovementModel.objects.filter(
            farm=farm,
            movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
            source_model=production._meta.label,
            source_id=str(production.pk),
        ).select_related("ingredient").order_by("ingredient__name", "id")
        requirements = []
        for movement in movements:
            requirements.append(IngredientRequirement(
                ingredient_id=movement.ingredient_id,
                name=movement.ingredient.name,
                is_in_bin=movement.ingredient.is_in_bin,
                percentage=Decimal("0.00"),
                required_kg=abs(movement.quantity_kg),
            ))
        return requirements

    @transaction.atomic
    def refresh_delivery_remaining(self, delivery: DeliveryModel) -> Decimal:
        delivery = DeliveryModel.objects.select_for_update().get(pk=delivery.pk)
        allocated = ProductionIngredientUsageModel.objects.filter(
            delivery=delivery,
        ).aggregate(total=Sum("quantity_kg"))["total"] or Decimal("0.00")
        remaining = self._quantize_kg(delivery.quantity_kg - allocated)
        if remaining < 0:
            raise ValidationError("Dostawa ma rozliczone więcej składnika niż jej ilość.")
        DeliveryModel.objects.filter(pk=delivery.pk).update(remaining_quantity_kg=remaining)
        delivery.remaining_quantity_kg = remaining
        return remaining

    @transaction.atomic
    def release_production(self, production: ProductionModel, *, remove_cost: bool = True) -> None:
        farm = self.farm or production.recipe.farm
        usages = (
            ProductionIngredientUsageModel.objects.select_for_update()
            .filter(
                farm=farm,
                production=production,
            )
            .order_by("id")
        )
        usage_ids = []
        for usage in usages:
            usage_ids.append(usage.pk)
            if usage.delivery_id:
                DeliveryModel.objects.filter(pk=usage.delivery_id).update(
                    remaining_quantity_kg=F("remaining_quantity_kg") + usage.quantity_kg,
                )
        if usage_ids:
            ProductionIngredientUsageModel.objects.filter(pk__in=usage_ids).delete()
        InventoryMovementModel.objects.filter(
            farm=farm,
            movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
            source_model=production._meta.label,
            source_id=str(production.pk),
        ).delete()
        ProductionModel.objects.filter(pk=production.pk).update(
            feed_cost_total=Decimal("0.00"),
            feed_cost_per_kg=Decimal("0.00000"),
            feed_cost_is_partial=False,
            feed_cost_note="",
        )
        if remove_cost:
            from costs.actions import delete_production_cost
            delete_production_cost(production)

    @transaction.atomic
    def book_production(
        self,
        production: ProductionModel,
        *,
        user=None,
        forced=False,
        prefer_existing_movements=False,
    ) -> int:
        production = (
            ProductionModel.objects.select_for_update()
            .select_related("recipe", "recipe_version")
            .prefetch_related("recipe__items__ingredient", "recipe_version__items__ingredient")
            .get(pk=production.pk)
        )
        farm = self.farm or production.recipe.farm
        if production.recipe.farm_id != farm.id:
            raise ValidationError("Produkcja nie należy do tego gospodarstwa.")

        if production.status != ProductionModel.Statuses.COMPLETED:
            self.release_production(production)
            return 0

        requirements = []
        if prefer_existing_movements:
            requirements = self._movement_requirements(production, farm)
        if not requirements:
            # Przy odbudowie FIFO bez starych ruchów rekonstruujemy zużycie z obecnej
            # receptury/custom_recipe_data. To najlepsze przybliżenie, nie dowód historii.
            requirements = list(self._production_requirements(production))

        self.release_production(production, remove_cost=False)

        usage_count = 0
        total_cost = Decimal("0.00")
        partial = False
        missing_messages = []
        for requirement in requirements:
            required_kg = self._quantize_kg(abs(requirement.required_kg))
            if required_kg <= 0:
                continue

            remaining_to_allocate = required_kg
            ingredient_cost = Decimal("0.00")
            deliveries = DeliveryModel.objects.select_for_update().filter(
                ingredient_id=requirement.ingredient_id,
                ingredient__farm=farm,
                date__lte=production.date,
                price_per_kg__isnull=False,
                price_per_kg__gt=0,
                remaining_quantity_kg__gt=0,
            ).order_by("date", "id")

            for delivery in deliveries:
                if remaining_to_allocate <= 0:
                    break
                available = self._quantize_kg(delivery.remaining_quantity_kg)
                if available <= 0:
                    continue
                quantity = min(available, remaining_to_allocate)
                quantity = self._quantize_kg(quantity)
                unit_price = delivery.price_per_kg
                cost = self._quantize_money(quantity * unit_price)
                ProductionIngredientUsageModel.objects.create(
                    farm=farm,
                    production=production,
                    ingredient_id=requirement.ingredient_id,
                    delivery=delivery,
                    quantity_kg=quantity,
                    unit_price=unit_price,
                    cost=cost,
                )
                usage_count += 1
                ingredient_cost += cost
                remaining_to_allocate = self._quantize_kg(remaining_to_allocate - quantity)
                delivery.remaining_quantity_kg = self._quantize_kg(delivery.remaining_quantity_kg - quantity)
                delivery.save(update_fields=["remaining_quantity_kg"])

            if remaining_to_allocate > 0:
                partial = True
                missing_messages.append(f"{requirement.name}: {format_mass(remaining_to_allocate)}")
                if not forced:
                    raise ValidationError(
                        "Brakuje rozliczalnych dostaw FIFO dla produkcji: "
                        + ", ".join(missing_messages)
                    )

            movement_unit_price = None
            if ingredient_cost > 0 and required_kg > 0:
                movement_unit_price = self._quantize_price(ingredient_cost / required_kg)
            InventoryMovementModel.objects.create(
                farm=farm,
                ingredient_id=requirement.ingredient_id,
                movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
                source_model=production._meta.label,
                source_id=str(production.pk),
                quantity_kg=-required_kg,
                unit_price=movement_unit_price,
                movement_date=production.date,
                created_by=user if getattr(user, "is_authenticated", False) else None,
                note="Zużycie do produkcji FIFO"
                if not forced
                else "Wymuszone zatwierdzenie produkcji FIFO",
            )
            total_cost += ingredient_cost

        cost_per_kg = Decimal("0.00000")
        if production.quantity_kg:
            cost_per_kg = self._quantize_price(total_cost / production.quantity_kg)
        note = ""
        if partial:
            note = "Częściowy koszt - brak rozliczalnych dostaw FIFO: " + ", ".join(missing_messages)
        ProductionModel.objects.filter(pk=production.pk).update(
            feed_cost_total=self._quantize_money(total_cost),
            feed_cost_per_kg=cost_per_kg,
            feed_cost_is_partial=partial,
            feed_cost_note=note[:255],
        )
        production.feed_cost_total = self._quantize_money(total_cost)
        production.feed_cost_per_kg = cost_per_kg
        production.feed_cost_is_partial = partial
        production.feed_cost_note = note[:255]
        from costs.actions import sync_production_cost
        sync_production_cost(production, user=user)
        return usage_count

    @transaction.atomic
    def adjust(
        self,
        *,
        ingredient: IngredientModel,
        quantity_kg: Decimal,
        direction: str,
        movement_date: date,
        reason: str,
        user=None,
    ) -> InventoryMovementModel:
        ingredient = IngredientModel.objects.select_for_update().get(pk=ingredient.pk, farm=self.farm)
        quantity = abs(Decimal(quantity_kg))
        if quantity <= 0:
            raise ValidationError("Ilość korekty musi być większa od zera.")
        if direction == "minus":
            current = self.balances().get(ingredient.pk, Decimal("0.00"))
            if quantity > current:
                raise ValidationError("Korekta spowodowałaby ujemny stan magazynowy.")
            movement_type = InventoryMovementModel.Types.ADJUSTMENT_NEGATIVE
            signed_quantity = -quantity
        elif direction == "plus":
            movement_type = InventoryMovementModel.Types.ADJUSTMENT_POSITIVE
            signed_quantity = quantity
        else:
            raise ValidationError("Nieprawidłowy typ korekty.")
        movement = InventoryMovementModel.objects.create(
            farm=self.farm,
            ingredient=ingredient,
            movement_type=movement_type,
            quantity_kg=signed_quantity,
            movement_date=movement_date,
            note=reason,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        invalidate_farm_cache_on_commit(self.farm, groups=("inventory",))
        return movement

    @transaction.atomic
    def rebuild(
        self,
        *,
        prefer_existing_movements: bool = True,
        reconstruct_production_ids: set[int] | None = None,
    ) -> dict[str, int]:
        reconstruct_production_ids = reconstruct_production_ids or set()
        from costs.actions import delete_stale_production_costs
        delete_stale_production_costs(self.farm)
        ProductionIngredientUsageModel.objects.filter(farm=self.farm).delete()
        DeliveryModel.objects.filter(ingredient__farm=self.farm).update(remaining_quantity_kg=F("quantity_kg"))
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type=InventoryMovementModel.Types.DELIVERY,
        ).delete()
        delivery_count = 0
        for delivery in DeliveryModel.objects.filter(ingredient__farm=self.farm).select_related("ingredient"):
            try:
                self.sync_delivery(delivery)
            except Exception as error:
                raise InventoryRebuildError(
                    "Błąd synchronizacji dostawy podczas odbudowy FIFO",
                    farm=self.farm,
                ) from error
            delivery_count += 1
        production_count = 0
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe", "recipe_version").prefetch_related(
            "recipe__items__ingredient",
            "recipe_version__items__ingredient",
        ).order_by("date", "time", "id")
        production_ids = [str(pk) for pk in productions.values_list("pk", flat=True)]
        for production in productions:
            try:
                production_count += self.book_production(
                    production,
                    forced=True,
                    prefer_existing_movements=(
                        prefer_existing_movements
                        and production.pk not in reconstruct_production_ids
                    ),
                )
            except Exception as error:
                raise InventoryRebuildError(
                    "Błąd rozliczenia produkcji podczas odbudowy FIFO",
                    farm=self.farm,
                    production=production,
                ) from error
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        ).exclude(source_id__in=production_ids).delete()
        return {"deliveries": delivery_count, "production_movements": production_count}
