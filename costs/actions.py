from decimal import Decimal

from django.db import transaction

from costs.models import CostCategoryModel, CostModel
from farms.services.cache import invalidate_farm_cache_on_commit
from common.units import format_mass


FEED_COST_CATEGORY_NAME = "Pasza"
FEED_COST_CATEGORY_DESCRIPTION = "Automatyczne koszty zakończonych śrutowań rozliczone według FIFO."


def production_cost_description(production) -> str:
    return f"Pasza – śrutowanie {production.recipe.name} ({format_mass(production.quantity_kg)})"


@transaction.atomic
def sync_production_cost(production, *, user=None):
    farm = production.recipe.farm
    if production.status != production.Statuses.COMPLETED:
        delete_production_cost(production)
        return None

    category = CostCategoryModel.objects.select_for_update().filter(
        farm=farm,
        name__iexact=FEED_COST_CATEGORY_NAME,
    ).first()
    if category is None:
        category = CostCategoryModel.objects.create(
            farm=farm,
            name=FEED_COST_CATEGORY_NAME,
            description=FEED_COST_CATEGORY_DESCRIPTION,
        )
    if not category.is_active:
        category.is_active = True
        category.save(update_fields=("is_active", "updated_at"))

    defaults = {
        "farm": farm,
        "category": category,
        "date": production.date,
        "amount": Decimal(production.feed_cost_total or 0).quantize(Decimal("0.01")),
        "description": production_cost_description(production),
        "document_number": f"ŚRUTOWANIE/{production.pk}",
        "supplier": "",
        "is_paid": True,
    }
    cost, created = CostModel.objects.select_for_update().get_or_create(
        production=production,
        defaults={
            **defaults,
            "created_by": user if getattr(user, "is_authenticated", False) else None,
        },
    )
    if not created:
        for field, value in defaults.items():
            setattr(cost, field, value)
        cost.save(update_fields=(*defaults.keys(), "updated_at"))
    invalidate_farm_cache_on_commit(farm, groups=("costs",))
    return cost


@transaction.atomic
def delete_production_cost(production) -> None:
    if not production.pk:
        return
    farm = production.recipe.farm
    deleted, _ = CostModel.objects.filter(
        farm=farm,
        production_id=production.pk,
    ).delete()
    if deleted:
        invalidate_farm_cache_on_commit(farm, groups=("costs",))


@transaction.atomic
def delete_stale_production_costs(farm) -> int:
    stale = CostModel.objects.filter(
        farm=farm,
        production__isnull=False,
    ).exclude(production__status="COMPLETED")
    deleted, _ = stale.delete()
    if deleted:
        invalidate_farm_cache_on_commit(farm, groups=("costs",))
    return deleted
