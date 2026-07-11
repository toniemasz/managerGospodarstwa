from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from farms.services.cache import invalidate_farm_cache_on_commit
from feed.actions.inventory import InventoryActions
from feed.actions.finished_feed import create_feed_serving, create_finished_feed_batch_for_production, production_is_ready_feed
from feed.models import ProductionModel
from feed.selectors.productions import production_for_processing, validate_production_capacity


def create_production(form):
    with transaction.atomic():
        production = form.save()
        invalidate_farm_cache_on_commit(production.recipe.farm, groups=("feed",))
        return production


@transaction.atomic
def mark_stage_1_done(farm, production_id: int) -> tuple[bool, str]:
    production = production_for_processing(farm, production_id, lock_for_update=True)
    if production.status != ProductionModel.Statuses.QUEUED:
        return False, "Śrutowanie nie znajduje się w kolejce początkowej."

    production.status = ProductionModel.Statuses.STAGE_1_DONE
    production.save(update_fields=("status",))
    invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return True, "Zakończono pobieranie z binów. Gotowe do Etapu 2."


def completion_datetime_for(production_date, *, now=None):
    """Zwraca czas zakończenia z datą planu i lokalną godziną wykonania."""
    current = now or timezone.now()
    if timezone.is_aware(current):
        local_current = timezone.localtime(current)
        local_time = local_current.timetz().replace(tzinfo=None)
        naive_completion = datetime.combine(production_date, local_time)
        return timezone.make_aware(naive_completion, timezone.get_current_timezone())
    return datetime.combine(production_date, current.time())


def complete_production(
    farm,
    production_id: int,
    *,
    skip_stages: bool = False,
    force_inventory: bool = False,
    user=None,
    create_serving: bool | None = None,
) -> tuple[bool, str]:
    try:
        with transaction.atomic():
            production = production_for_processing(farm, production_id, lock_for_update=True)
            farm = farm or production.recipe.farm

            if production.status == ProductionModel.Statuses.COMPLETED:
                return False, "To śrutowanie zostało już wcześniej zaksięgowane."

            if not skip_stages and production.status != ProductionModel.Statuses.STAGE_1_DONE:
                return False, "Nie można zakończyć produkcji przed wykonaniem Etapu 1."

            if not force_inventory:
                is_possible, errors = validate_production_capacity(farm, production_id)
                if not is_possible:
                    return False, "Brak wystarczającej ilości składników na magazynie: " + " | ".join(errors)

            production.status = ProductionModel.Statuses.COMPLETED
            production.completed_at = completion_datetime_for(production.date)
            production._skip_inventory_sync = True
            production.save(update_fields=("status", "completed_at"))
            InventoryActions(farm).book_production(
                production,
                user=user,
                forced=force_inventory,
            )
            production.refresh_from_db()
            from farms.models import FarmSettingsModel
            from farms.services.settings_service import get_farm_settings
            get_farm_settings(farm)
            settings = FarmSettingsModel.objects.select_for_update().get(farm=farm)
            is_ready_feed = production_is_ready_feed(production)
            should_serve = is_ready_feed or (
                settings.feed_serving_mode == FarmSettingsModel.FeedServingModes.AUTO_FULL_PRODUCTION
                if create_serving is None else create_serving
            )
            mode_used = (
                FarmSettingsModel.FeedServingModes.AUTO_FULL_PRODUCTION
                if should_serve else FarmSettingsModel.FeedServingModes.MANUAL
            )
            production.completion_feed_serving_mode = mode_used
            production.save(update_fields=("completion_feed_serving_mode",))
            batch = create_finished_feed_batch_for_production(production)
            if should_serve:
                create_feed_serving(
                    farm=farm, product=batch.product, date=production.date,
                    quantity_kg=production.quantity_kg, user=user,
                    automatic_for_production=production,
                )
            invalidate_farm_cache_on_commit(farm, groups=("feed",))
    except ValidationError as error:
        message = error.messages[0] if hasattr(error, "messages") else str(error)
        return False, message
    if should_serve:
        return True, f"Produkcja zakończona. Utworzono {production.quantity_kg:.2f} kg gotowej paszy i zarejestrowano automatyczne podanie."
    return True, f"Produkcja zakończona. Utworzono {production.quantity_kg:.2f} kg gotowej paszy. Pasza pozostała na magazynie."


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
    force_inventory: bool = False,
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
            force_inventory=force_inventory,
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
        production = form.save()
        invalidate_farm_cache_on_commit(production.recipe.farm, groups=("feed",))
        return production


def delete_production_with_inventory(farm, production):
    with transaction.atomic():
        InventoryActions(farm).release_production(production)
        production.delete()
        invalidate_farm_cache_on_commit(farm, groups=("feed",))
