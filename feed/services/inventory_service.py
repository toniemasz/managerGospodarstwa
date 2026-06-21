from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from feed.models import DeliveryModel, IngredientModel, InventoryMovementModel, ProductionModel
from feed.services.feed_calculators import ProductionCalculator


@dataclass(frozen=True)
class InventoryBalance:
    ingredient_id: int
    quantity_kg: Decimal


class InventoryMovementService:
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

    def movement_totals(self) -> dict[int, tuple[Decimal, Decimal]]:
        queryset = InventoryMovementModel.objects.all()
        if self.farm is not None:
            queryset = queryset.filter(farm=self.farm)
        totals: dict[int, tuple[Decimal, Decimal]] = {}
        for ingredient_id, quantity in queryset.values_list("ingredient_id", "quantity_kg"):
            positive, negative = totals.get(ingredient_id, (Decimal("0.00"), Decimal("0.00")))
            if quantity > 0:
                positive += quantity
            else:
                negative += abs(quantity)
            totals[ingredient_id] = (positive, negative)
        return totals

    @transaction.atomic
    def sync_delivery(self, delivery: DeliveryModel, *, user=None) -> InventoryMovementModel:
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
        return movement

    @transaction.atomic
    def remove_delivery(self, delivery: DeliveryModel) -> None:
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type=InventoryMovementModel.Types.DELIVERY,
            source_model=delivery._meta.label,
            source_id=str(delivery.pk),
        ).delete()

    @staticmethod
    def _production_requirements(production: ProductionModel):
        items = [
            {
                "ingredient_id": item.ingredient_id,
                "name": item.ingredient.name,
                "is_in_bin": item.ingredient.is_in_bin,
                "percentage": item.percentage,
            }
            for item in production.recipe.items.select_related("ingredient")
        ]
        return ProductionCalculator(
            quantity_kg=production.quantity_kg,
            base_recipe_items=items,
            custom_recipe_data=production.custom_recipe_data,
        ).get_requirements()

    @transaction.atomic
    def book_production(self, production: ProductionModel, *, user=None, forced=False) -> int:
        farm = self.farm or production.recipe.farm
        if production.recipe.farm_id != farm.id:
            raise ValidationError("Produkcja nie należy do tego gospodarstwa.")
        requirements = list(self._production_requirements(production))
        ingredient_ids = [item.ingredient_id for item in requirements]
        stale = InventoryMovementModel.objects.filter(
            farm=farm,
            movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
            source_model=production._meta.label,
            source_id=str(production.pk),
        )
        if ingredient_ids:
            stale = stale.exclude(ingredient_id__in=ingredient_ids)
        stale.delete()
        count = 0
        for requirement in requirements:
            movement, created = InventoryMovementModel.objects.update_or_create(
                farm=farm,
                ingredient_id=requirement.ingredient_id,
                movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
                source_model=production._meta.label,
                source_id=str(production.pk),
                defaults={
                    "quantity_kg": -abs(requirement.required_kg),
                    "movement_date": production.date,
                    "created_by": user if getattr(user, "is_authenticated", False) else None,
                    "note": "Wymuszone zatwierdzenie produkcji" if forced else "Zużycie do produkcji",
                },
            )
            count += int(created)
        return count

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
        return InventoryMovementModel.objects.create(
            farm=self.farm,
            ingredient=ingredient,
            movement_type=movement_type,
            quantity_kg=signed_quantity,
            movement_date=movement_date,
            note=reason,
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )

    @transaction.atomic
    def rebuild(self) -> dict[str, int]:
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type__in=(
                InventoryMovementModel.Types.DELIVERY,
                InventoryMovementModel.Types.PRODUCTION_USAGE,
            ),
        ).delete()
        delivery_count = 0
        for delivery in DeliveryModel.objects.filter(ingredient__farm=self.farm).select_related("ingredient"):
            self.sync_delivery(delivery)
            delivery_count += 1
        production_count = 0
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe").prefetch_related("recipe__items__ingredient")
        for production in productions:
            production_count += self.book_production(production)
        return {"deliveries": delivery_count, "production_movements": production_count}
