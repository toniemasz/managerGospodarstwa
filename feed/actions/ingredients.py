from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit


class IngredientNameConflictError(ValidationError):
    pass


@dataclass(frozen=True)
class DeletedIngredient:
    model_label: str
    object_id: int
    object_repr: str


@transaction.atomic
def create_ingredient(form, *, farm):
    farm.__class__.objects.select_for_update().get(pk=farm.pk)
    ingredient = form.save(commit=False)
    ingredient.farm = farm
    ingredient.name = ingredient.name.strip()
    if ingredient.__class__.objects.filter(farm=farm, name__iexact=ingredient.name).exists():
        raise IngredientNameConflictError("Taki składnik istnieje już w tym gospodarstwie.")
    ingredient.save()
    invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return ingredient


@transaction.atomic
def update_ingredient(form):
    ingredient = form.save(commit=False)
    ingredient.farm.__class__.objects.select_for_update().get(pk=ingredient.farm_id)
    ingredient.name = ingredient.name.strip()
    if ingredient.__class__.objects.filter(
        farm=ingredient.farm,
        name__iexact=ingredient.name,
    ).exclude(pk=ingredient.pk).exists():
        raise IngredientNameConflictError("Taki składnik istnieje już w tym gospodarstwie.")
    ingredient.save()
    invalidate_farm_cache_on_commit(ingredient.farm, groups=("feed",))
    return ingredient


@transaction.atomic
def delete_ingredient(ingredient) -> DeletedIngredient:
    farm = ingredient.farm
    deleted_ingredient = DeletedIngredient(
        model_label=ingredient._meta.label,
        object_id=ingredient.pk,
        object_repr=str(ingredient),
    )
    ingredient.delete()
    invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return deleted_ingredient
