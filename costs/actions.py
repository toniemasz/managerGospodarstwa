from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction

from costs.models import CostCategoryModel, CostModel
from common.cache import invalidate_farm_cache_on_commit
from common.units import format_mass
from common.money import quantize_money

if TYPE_CHECKING:
    from feed.domain.production import ProductionCostResult


FEED_COST_CATEGORY_NAME = "Pasza"
FEED_COST_CATEGORY_DESCRIPTION = "Automatyczne koszty zakończonych śrutowań rozliczone według FIFO."


class CostCategoryNameConflictError(ValidationError):
    pass


@transaction.atomic
def save_manual_cost(*, farm, form, user=None):
    cost = form.save(commit=False)
    if cost.production_id:
        raise ValidationError("Koszt produkcji paszy nie może być zapisany jako koszt ręczny.")
    if cost.farm_id and cost.farm_id != farm.id:
        raise ValidationError("Koszt nie należy do wskazanego gospodarstwa.")
    cost.farm = farm
    if not cost.created_by_id and getattr(user, "is_authenticated", False):
        cost.created_by = user
    cost.full_clean()
    cost.save()
    invalidate_farm_cache_on_commit(farm, groups=("costs",))
    return cost


@transaction.atomic
def delete_manual_cost(*, farm, cost_id: int):
    cost = CostModel.objects.select_for_update().get(pk=cost_id, farm=farm)
    if cost.production_id:
        raise ValidationError("Koszt produkcji paszy nie może być usunięty ręcznie.")
    snapshot = {
        "model_label": cost._meta.label,
        "object_id": cost.pk,
        "object_repr": str(cost),
    }
    cost.delete()
    invalidate_farm_cache_on_commit(farm, groups=("costs",))
    return snapshot


@transaction.atomic
def save_cost_category(*, farm, form):
    farm.__class__.objects.select_for_update().get(pk=farm.pk)
    category = form.save(commit=False)
    if category.farm_id and category.farm_id != farm.id:
        raise ValidationError("Kategoria nie należy do wskazanego gospodarstwa.")
    category.farm = farm
    category.name = category.name.strip()
    if CostCategoryModel.objects.filter(
        farm=farm,
        name__iexact=category.name,
    ).exclude(pk=category.pk).exists():
        raise CostCategoryNameConflictError("Kategoria o tej nazwie już istnieje.")
    category.full_clean()
    category.save()
    invalidate_farm_cache_on_commit(farm, groups=("costs",))
    return category


@transaction.atomic
def deactivate_cost_category(*, farm, category_id: int):
    category = CostCategoryModel.objects.select_for_update().get(pk=category_id, farm=farm)
    category.is_active = False
    category.save(update_fields=("is_active", "updated_at"))
    invalidate_farm_cache_on_commit(farm, groups=("costs",))
    return category


def production_cost_description(production) -> str:
    return f"Pasza – śrutowanie {production.recipe.name} ({format_mass(production.quantity_kg)})"


@transaction.atomic
def sync_production_cost(*, farm, production, cost_result: "ProductionCostResult | None" = None, user=None):
    if production.recipe.farm_id != farm.id:
        raise ValidationError("Nie można zsynchronizować kosztu produkcji z innego gospodarstwa.")
    if production.status != production.Statuses.COMPLETED:
        delete_production_cost(farm=farm, production=production)
        return None

    category = CostCategoryModel.objects.select_for_update().filter(
        farm=farm,
        name__iexact=FEED_COST_CATEGORY_NAME,
    ).first()
    if category is None:
        category, _ = CostCategoryModel.objects.get_or_create(
            farm=farm,
            name=FEED_COST_CATEGORY_NAME,
            defaults={"description": FEED_COST_CATEGORY_DESCRIPTION},
        )
    if not category.is_active:
        category.is_active = True
        category.save(update_fields=("is_active", "updated_at"))

    amount = quantize_money(
        cost_result.total_cost if cost_result is not None else production.feed_cost_total or 0
    )
    defaults = {
        "farm": farm,
        "category": category,
        "date": production.date,
        "amount": amount,
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
def delete_production_cost(*, farm, production) -> None:
    if not production.pk:
        return
    if production.recipe.farm_id != farm.id:
        raise ValidationError("Nie można usunąć kosztu produkcji z innego gospodarstwa.")
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
