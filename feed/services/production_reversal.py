from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from costs.actions import delete_production_cost
from farms.services.audit_log_service import log_action
from common.cache import invalidate_farm_cache_on_commit
from feed.actions.finished_feed import delete_feed_serving
from feed.actions.inventory import InventoryActions
from feed.models import ProductionModel
from feed.services.reconciliation import ProductionReconciliationWorkflow


@dataclass(frozen=True)
class ProductionReversalResult:
    production_id: int
    previous_status: str
    new_status: str


class ProductionSettlementReversalWorkflow:
    def __init__(self, *, farm, user=None):
        if farm is None:
            raise ValueError("Cofnięcie rozliczenia wymaga jawnego gospodarstwa.")
        self.farm = farm
        self.user = user

    @transaction.atomic
    def reverse(self, production_id: int, *, reason: str) -> ProductionReversalResult:
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("Cofnięcie rozliczenia wymaga podania przyczyny.")
        production = ProductionModel.objects.select_for_update().select_related("recipe").get(
            pk=production_id,
            recipe__farm=self.farm,
        )
        if production.status != ProductionModel.Statuses.COMPLETED:
            raise ValidationError("Cofnąć można wyłącznie zakończoną produkcję.")

        batch = getattr(production, "finished_feed_batch", None)
        automatic_serving = getattr(production, "automatic_feed_serving", None)
        if batch is not None:
            allocations = batch.serving_allocations.all()
            if automatic_serving is not None:
                allocations = allocations.exclude(serving=automatic_serving)
            if allocations.exists():
                raise ValidationError(
                    "Nie można cofnąć produkcji, ponieważ jej partia została wykorzystana w innym podaniu."
                )
        if automatic_serving is not None:
            delete_feed_serving(farm=self.farm, serving=automatic_serving)

        InventoryActions(self.farm).release_production(production, remove_cost=False)
        delete_production_cost(farm=self.farm, production=production)
        if batch is not None:
            batch.delete()
        ProductionModel.objects.filter(pk=production.pk).update(
            status=ProductionModel.Statuses.STAGE_1_DONE,
            completed_at=None,
            completion_feed_serving_mode="",
        )
        production.status = ProductionModel.Statuses.STAGE_1_DONE
        production.completed_at = None
        production.completion_feed_serving_mode = ""

        ProductionReconciliationWorkflow(self.farm).rebuild()
        log_action(
            farm=self.farm,
            user=self.user,
            action="PRODUCTION_SETTLEMENT_REVERSED",
            obj=production,
            metadata={"reason": reason},
        )
        invalidate_farm_cache_on_commit(self.farm, groups=("feed", "inventory", "costs"))
        return ProductionReversalResult(
            production_id=production.pk,
            previous_status=ProductionModel.Statuses.COMPLETED,
            new_status=ProductionModel.Statuses.STAGE_1_DONE,
        )
