from django.db import transaction
from django.db.models import F

from costs.actions import delete_stale_production_costs, sync_production_cost
from feed.actions.finished_feed import create_finished_feed_batch_for_production
from feed.actions.inventory import InventoryActions, InventoryRebuildError
from feed.models import (
    DeliveryModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
)


class ProductionReconciliationWorkflow:
    def __init__(self, farm):
        if farm is None:
            raise ValueError("Uzgadnianie produkcji wymaga jawnego gospodarstwa.")
        self.farm = farm
        self.inventory = InventoryActions(farm)

    @transaction.atomic
    def rebuild(
        self,
        *,
        prefer_existing_movements: bool = True,
        reconstruct_production_ids: set[int] | None = None,
    ) -> dict[str, int]:
        reconstruct_production_ids = reconstruct_production_ids or set()
        delete_stale_production_costs(self.farm)
        ProductionIngredientUsageModel.objects.filter(farm=self.farm).delete()
        DeliveryModel.objects.filter(ingredient__farm=self.farm).update(remaining_quantity_kg=F("quantity_kg"))
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type=InventoryMovementModel.Types.DELIVERY,
        ).delete()

        delivery_count = self._rebuild_deliveries()
        production_count, production_ids = self._rebuild_productions(
            prefer_existing_movements=prefer_existing_movements,
            reconstruct_production_ids=reconstruct_production_ids,
        )
        InventoryMovementModel.objects.filter(
            farm=self.farm,
            movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        ).exclude(source_id__in=production_ids).delete()
        return {"deliveries": delivery_count, "production_movements": production_count}

    @transaction.atomic
    def rebuild_from_date(self, date_from) -> dict[str, int]:
        """Odbudowuje FIFO od daty zmiany, bez naruszania wcześniejszej historii."""
        productions = list(
            ProductionModel.objects.select_for_update(of=("self",))
            .filter(
                recipe__farm=self.farm,
                status=ProductionModel.Statuses.COMPLETED,
                date__gte=date_from,
            )
            .select_related("recipe")
            .order_by("date", "time", "id")
        )
        usage_count = 0
        for production in productions:
            try:
                result = self.inventory.book_production(
                    production,
                    forced=True,
                    prefer_existing_movements=True,
                )
                sync_production_cost(
                    farm=self.farm,
                    production=production,
                    cost_result=result,
                )
                production.refresh_from_db()
                create_finished_feed_batch_for_production(production)
                usage_count += result.usage_count
            except Exception as error:
                raise InventoryRebuildError(
                    "Błąd rozliczenia produkcji podczas częściowej odbudowy FIFO",
                    farm=self.farm,
                    production=production,
                ) from error
        return {
            "productions": len(productions),
            "production_movements": usage_count,
        }

    def _rebuild_deliveries(self) -> int:
        count = 0
        deliveries = DeliveryModel.objects.filter(
            ingredient__farm=self.farm,
        ).select_related("ingredient").order_by("date", "id")
        for delivery in deliveries:
            try:
                self.inventory.sync_delivery(delivery)
            except Exception as error:
                raise InventoryRebuildError(
                    "Błąd synchronizacji dostawy podczas odbudowy FIFO",
                    farm=self.farm,
                ) from error
            count += 1
        return count

    def _rebuild_productions(self, *, prefer_existing_movements, reconstruct_production_ids):
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe", "recipe_version").prefetch_related(
            "recipe__items__ingredient",
            "recipe_version__items__ingredient",
        ).order_by("date", "time", "id")
        production_ids = [str(pk) for pk in productions.values_list("pk", flat=True)]
        count = 0
        for production in productions:
            try:
                # Tryb forced jest celowo ograniczony do tej administracyjnej
                # odbudowy historycznego FIFO; żaden publiczny endpoint go nie udostępnia.
                result = self.inventory.book_production(
                    production,
                    forced=True,
                    prefer_existing_movements=(
                        prefer_existing_movements
                        and production.pk not in reconstruct_production_ids
                    ),
                )
                sync_production_cost(farm=self.farm, production=production, cost_result=result)
                production.refresh_from_db()
                create_finished_feed_batch_for_production(production)
                count += result.usage_count
            except Exception as error:
                raise InventoryRebuildError(
                    "Błąd rozliczenia produkcji podczas odbudowy FIFO",
                    farm=self.farm,
                    production=production,
                ) from error
        return count, production_ids
