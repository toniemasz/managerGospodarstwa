from django.core.exceptions import ValidationError
from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit
from feed.actions.inventory import InventoryActions
from feed.domain.exceptions import FeedDomainError
from feed.domain.production import completion_datetime_for
from feed.models import ProductionModel
from feed.selectors.productions import production_for_processing
from feed.services.production_completion import ProductionCompletionWorkflow
from feed.services.production_reversal import ProductionSettlementReversalWorkflow
from feed.actions.recipe_versions import RecipeVersionActions
import logging

from django.core.exceptions import ValidationError
from django.db import DatabaseError

logger = logging.getLogger(__name__)

def create_production(form):
    with transaction.atomic():
        production = form.save(commit=False)
        version, _ = RecipeVersionActions(farm=production.recipe.farm).ensure_current_version(
            production.recipe,
        )
        production.recipe_version = version
        production.save()
        invalidate_farm_cache_on_commit(production.recipe.farm, groups=("feed",))
        return production


@transaction.atomic
def mark_stage_1_done(farm, production_id: int) -> tuple[bool, str]:
    if farm is None:
        raise ValueError("Zmiana etapu produkcji wymaga jawnego gospodarstwa.")
    production = production_for_processing(farm, production_id, lock_for_update=True)
    if production.status != ProductionModel.Statuses.QUEUED:
        return False, "Śrutowanie nie znajduje się w kolejce początkowej."

    production.status = ProductionModel.Statuses.STAGE_1_DONE
    production.save(update_fields=("status",))
    invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return True, "Zakończono pobieranie z binów. Gotowe do Etapu 2."





def complete_production(
    farm,
    production_id: int,
    *,
    skip_stages: bool = False,
    user=None,
) -> tuple[bool, str]:
    if farm is None:
        raise ValueError("Zakończenie produkcji wymaga jawnego gospodarstwa.")

    try:
        result = ProductionCompletionWorkflow(
            farm=farm,
            user=user,
        ).complete(
            production_id,
            skip_stages=skip_stages,
        )
    except (ValidationError, FeedDomainError) as error:
        message = error.messages[0] if hasattr(error, "messages") else str(error)
        return False, message
    except DatabaseError:
        logger.exception(
            "Błąd bazy podczas zakończenia produkcji",
            extra={
                "farm_id": farm.pk,
                "production_id": production_id,
            },
        )
        return False, (
            "Nie udało się zakończyć śrutowania z powodu błędu danych. "
            "Szczegóły zapisano w logach."
        )
    return True, result.message


def _normalize_production_ids(production_ids) -> tuple[set[int], int]:
    normalized = set()
    invalid_count = 0
    for raw_id in production_ids:
        try:
            production_id = int(raw_id)
        except (TypeError, ValueError):
            invalid_count += 1
            continue
        if production_id <= 0:
            invalid_count += 1
            continue
        normalized.add(production_id)
    return normalized, invalid_count


def bulk_complete_productions(
    farm,
    production_ids,
    *,
    user=None,
) -> dict:
    normalized_ids, invalid_count = _normalize_production_ids(production_ids)
    result = {
        "completed_ids": [],
        "already_completed": [],
        "failed": [],
        "unavailable_count": invalid_count,
    }
    if not normalized_ids:
        return result

    productions = list(
        ProductionModel.objects.filter(
            pk__in=normalized_ids,
            recipe__farm=farm,
        )
        .select_related("recipe")
        .order_by("date", "time", "id")
    )
    result["unavailable_count"] += len(normalized_ids) - len(productions)

    for production in productions:
        if production.status == ProductionModel.Statuses.COMPLETED:
            result["already_completed"].append(production.pk)
            continue

        success, message = complete_production(
            farm,
            production.pk,
            skip_stages=production.status == ProductionModel.Statuses.QUEUED,
            user=user,
        )
        if success:
            result["completed_ids"].append(production.pk)
            continue

        current_status = ProductionModel.objects.filter(
            pk=production.pk,
            recipe__farm=farm,
        ).values_list("status", flat=True).first()
        if current_status == ProductionModel.Statuses.COMPLETED:
            result["already_completed"].append(production.pk)
            continue

        result["failed"].append({
            "id": production.pk,
            "label": f"{production.recipe.name} ({production.date:%d.%m.%Y})",
            "message": message,
        })

    return result


def update_production(form):
    with transaction.atomic():
        previous_recipe_id = None
        if form.instance.pk:
            current = ProductionModel.objects.select_for_update().get(
                pk=form.instance.pk,
                recipe__farm=form.instance.recipe.farm,
            )
            if current.status == ProductionModel.Statuses.COMPLETED:
                raise ValidationError(
                    "Zakończonej produkcji nie można edytować bez kontrolowanego cofnięcia rozliczenia."
                )
            previous_recipe_id = current.recipe_id
        production = form.save(commit=False)
        if production.recipe_version_id is None or production.recipe_id != previous_recipe_id:
            version, _ = RecipeVersionActions(farm=production.recipe.farm).ensure_current_version(
                production.recipe,
            )
            production.recipe_version = version
        production.save()
        invalidate_farm_cache_on_commit(production.recipe.farm, groups=("feed",))
        return production


def delete_production_with_inventory(farm, production):
    if farm is None:
        raise ValueError("Usunięcie produkcji wymaga jawnego gospodarstwa.")
    with transaction.atomic():
        production = ProductionModel.objects.select_for_update().select_related("recipe").get(
            pk=production.pk,
            recipe__farm=farm,
        )
        if production.status == ProductionModel.Statuses.COMPLETED:
            ProductionSettlementReversalWorkflow(farm=farm).reverse(
                production.pk,
                reason="Usunięcie produkcji",
            )
            production.refresh_from_db()
        else:
            InventoryActions(farm).release_production(production)
        production.delete()
        invalidate_farm_cache_on_commit(farm, groups=("feed",))
