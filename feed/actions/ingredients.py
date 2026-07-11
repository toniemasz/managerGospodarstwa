from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit


@dataclass(frozen=True)
class DeletedIngredient:
    model_label: str
    object_id: int
    object_repr: str


def create_ingredient(form, *, farm):
    ingredient = form.save(commit=False)
    ingredient.farm = farm
    ingredient.save()
    invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return ingredient


def update_ingredient(form):
    ingredient = form.save()
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
