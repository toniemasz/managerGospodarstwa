from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction


@dataclass(frozen=True)
class DeletedIngredient:
    model_label: str
    object_id: int
    object_repr: str


def create_ingredient(form, *, farm):
    ingredient = form.save(commit=False)
    ingredient.farm = farm
    ingredient.save()
    return ingredient


def update_ingredient(form):
    return form.save()


@transaction.atomic
def delete_ingredient(ingredient) -> DeletedIngredient:
    deleted_ingredient = DeletedIngredient(
        model_label=ingredient._meta.label,
        object_id=ingredient.pk,
        object_repr=str(ingredient),
    )
    ingredient.delete()
    return deleted_ingredient
