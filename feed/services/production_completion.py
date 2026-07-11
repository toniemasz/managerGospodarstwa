from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from costs.actions import sync_production_cost
from farms.models import FarmSettingsModel
from farms.services.audit_log_service import log_action
from common.cache import invalidate_farm_cache_on_commit
from farms.services.settings_service import get_farm_settings
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
    serving_id: int | None
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
        force_inventory: bool = False,
        create_serving: bool | None = None,
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
        self._validate_forced_completion(force_inventory)

        production.status = ProductionModel.Statuses.COMPLETED
        production.completed_at = completion_datetime_for(production.date)
        production.save(update_fields=("status", "completed_at"))

        cost_result = InventoryActions(self.farm).book_production(
            production,
            user=self.user,
            forced=force_inventory,
        )
        production.refresh_from_db()
        sync_production_cost(
            farm=self.farm,
            production=production,
            cost_result=cost_result,
            user=self.user,
        )

        should_serve = self._should_create_serving(create_serving)
        production.completion_feed_serving_mode = (
            FarmSettingsModel.FeedServingModes.AUTO_FULL_PRODUCTION
            if should_serve
            else FarmSettingsModel.FeedServingModes.MANUAL
        )
        production.save(update_fields=("completion_feed_serving_mode",))

        batch = create_finished_feed_batch_for_production(production)
        serving = None
        if should_serve:
            serving = create_feed_serving(
                farm=self.farm,
                product=batch.product,
                date=production.date,
                time=production.time,
                quantity_kg=production.quantity_kg,
                user=self.user,
                automatic_for_production=production,
            )

        if force_inventory:
            log_action(
                farm=self.farm,
                user=self.user,
                action="PRODUCTION_FORCE_COMPLETED",
                obj=production,
                metadata={
                    "missing_components": list(cost_result.missing_components),
                    "partial_cost": cost_result.is_partial,
                },
            )
        invalidate_farm_cache_on_commit(self.farm, groups=("feed", "inventory", "costs"))
        message = self._completion_message(production, should_serve)
        return ProductionCompletionResult(
            production_id=production.pk,
            cost=cost_result,
            batch_id=batch.pk,
            serving_id=serving.pk if serving else None,
            message=message,
        )

    def _should_create_serving(self, explicit_choice: bool | None) -> bool:
        if explicit_choice is not None:
            return explicit_choice
        get_farm_settings(self.farm)
        settings = FarmSettingsModel.objects.select_for_update().get(farm=self.farm)
        return settings.feed_serving_mode == FarmSettingsModel.FeedServingModes.AUTO_FULL_PRODUCTION

    def _validate_forced_completion(self, force_inventory: bool) -> None:
        if not force_inventory:
            return
        is_farm_owner = self.user is not None and self.farm.owner_id == getattr(self.user, "pk", None)
        if not is_farm_owner and not getattr(self.user, "is_staff", False):
            raise FeedDomainError("Wymuszone zatwierdzenie produkcji wymaga uprawnień administratora.")

    @staticmethod
    def _completion_message(production, served: bool) -> str:
        if served:
            return (
                f"Produkcja zakończona. Utworzono {format_mass(production.quantity_kg)} "
                "gotowej paszy i zarejestrowano automatyczne podanie."
            )
        return (
            f"Produkcja zakończona. Utworzono {format_mass(production.quantity_kg)} "
            "gotowej paszy. Pasza pozostała na magazynie."
        )
