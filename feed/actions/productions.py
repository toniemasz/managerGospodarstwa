from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from feed.actions.inventory import InventoryActions
from feed.models import ProductionModel
from feed.selectors.productions import production_for_processing, validate_production_capacity


@transaction.atomic
def mark_stage_1_done(farm, production_id: int) -> tuple[bool, str]:
    production = production_for_processing(farm, production_id, lock_for_update=True)
    if production.status != ProductionModel.Statuses.QUEUED:
        return False, "Śrutowanie nie znajduje się w kolejce początkowej."

    production.status = ProductionModel.Statuses.STAGE_1_DONE
    production.save()
    return True, "Zakończono pobieranie z binów. Gotowe do Etapu 2."


def complete_production(
    farm,
    production_id: int,
    *,
    skip_stages: bool = False,
    force_inventory: bool = False,
    user=None,
) -> tuple[bool, str]:
    try:
        with transaction.atomic():
            production = production_for_processing(farm, production_id, lock_for_update=True)

            if production.status == ProductionModel.Statuses.COMPLETED:
                return False, "To śrutowanie zostało już wcześniej zaksięgowane."

            if not skip_stages and production.status != ProductionModel.Statuses.STAGE_1_DONE:
                return False, "Nie można zakończyć produkcji przed wykonaniem Etapu 1."

            if not force_inventory:
                is_possible, errors = validate_production_capacity(farm, production_id)
                if not is_possible:
                    return False, "Brak wystarczającej ilości składników na magazynie: " + " | ".join(errors)

            production.status = ProductionModel.Statuses.COMPLETED
            production.completed_at = timezone.now()
            production._skip_inventory_sync = True
            production.save()
            InventoryActions(farm).book_production(
                production,
                user=user,
                forced=force_inventory,
            )
    except ValidationError as error:
        message = error.messages[0] if hasattr(error, "messages") else str(error)
        return False, message
    return True, "Śrutowanie zakończone pomyślnie. Zaktualizowano stany magazynowe i koszt FIFO."


def update_production(form):
    with transaction.atomic():
        return form.save()


def delete_production_with_inventory(farm, production):
    with transaction.atomic():
        InventoryActions(farm).release_production(production)
        production.delete()
