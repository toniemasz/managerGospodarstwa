from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from costs.actions import sync_production_cost
from common.cache import invalidate_farm_cache_on_commit
from feed.actions.finished_feed import create_feed_serving, create_finished_feed_batch_for_production
from feed.actions.inventory import InventoryActions
from feed.domain.exceptions import FeedDomainError
from feed.domain.production import ProductionCostResult, completion_datetime_for, validate_completion_transition
from feed.models import ProductionModel
from feed.selectors.productions import production_for_processing
from common.units import format_mass


@dataclass(frozen=True)
class ProductionCompletionResult:
    production_id: int
    cost: ProductionCostResult
    batch_id: int
    serving_id: int
    message: str


class ProductionCompletionWorkflow:
    def __init__(self, *, farm, user=None):
        if farm is None:
            raise ValueError("Workflow zakończenia produkcji wymaga jawnego gospodarstwa.")
        self.farm = farm
        self.user = user

    @transaction.atomic
    def complete(
        self,
        production_id: int,
        *,
        skip_stages: bool = False,
    ) -> ProductionCompletionResult:
        production = production_for_processing(
            self.farm,
            production_id,
            lock_for_update=True,
        )
        validate_completion_transition(
            current_status=production.status,
            completed_status=ProductionModel.Statuses.COMPLETED,
            stage_one_status=ProductionModel.Statuses.STAGE_1_DONE,
            skip_stages=skip_stages,
        )
        production.status = ProductionModel.Statuses.COMPLETED
        production.completed_at = completion_datetime_for(production.date)
        production.save(update_fields=("status", "completed_at"))

        cost_result = InventoryActions(self.farm).book_production(
            production,
            user=self.user,
            forced=False,
        )
        production.refresh_from_db()
        sync_production_cost(
            farm=self.farm,
            production=production,
            cost_result=cost_result,
            user=self.user,
        )

        production.completion_feed_serving_mode = "AUTO_FULL_PRODUCTION"
        production.save(update_fields=("completion_feed_serving_mode",))

        batch = create_finished_feed_batch_for_production(production)
        serving = create_feed_serving(
            farm=self.farm,
            product=batch.product,
            date=production.date,
            time=production.time,
            quantity_kg=production.quantity_kg,
            user=self.user,
            automatic_for_production=production,
        )

        invalidate_farm_cache_on_commit(self.farm, groups=("feed", "inventory", "costs"))
        message = self._completion_message(production)
        return ProductionCompletionResult(
            production_id=production.pk,
            cost=cost_result,
            batch_id=batch.pk,
            serving_id=serving.pk,
            message=message,
        )

    @staticmethod
    def _completion_message(production) -> str:
        return (
            f"Produkcja zakończona. Utworzono {format_mass(production.quantity_kg)} "
            "gotowej paszy i zarejestrowano automatyczne podanie."
        )
