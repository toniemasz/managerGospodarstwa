from django.core.exceptions import ValidationError
from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit
from feed.actions.recipe_versions import RecipeVersionActions


class RecipeNameConflictError(ValidationError):
    pass


def _deleted_recipe_data(recipe) -> dict:
    return {
        "model_label": recipe._meta.label,
        "object_id": recipe.pk,
        "object_repr": str(recipe),
    }


def create_recipe(form, formset, *, farm, user=None):
    with transaction.atomic():
        farm.__class__.objects.select_for_update().get(pk=farm.pk)
        recipe = form.save(commit=False)
        recipe.farm = farm
        recipe.name = recipe.name.strip()
        if recipe.__class__.objects.filter(farm=farm, name__iexact=recipe.name).exists():
            raise RecipeNameConflictError("Taka receptura istnieje już w tym gospodarstwie.")
        recipe.save()
        formset.instance = recipe
        formset.save()
        RecipeVersionActions(farm=farm, user=user).ensure_current_version(
            recipe,
            change_note="Utworzenie receptury",
        )
        invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return recipe


def update_recipe(form, formset, *, farm, user=None):
    with transaction.atomic():
        farm.__class__.objects.select_for_update().get(pk=farm.pk)
        recipe = form.save(commit=False)
        recipe.name = recipe.name.strip()
        if recipe.__class__.objects.filter(
            farm=farm,
            name__iexact=recipe.name,
        ).exclude(pk=recipe.pk).exists():
            raise RecipeNameConflictError("Taka receptura istnieje już w tym gospodarstwie.")
        recipe.save()
        formset.save()
        _, version_created = RecipeVersionActions(farm=farm, user=user).ensure_current_version(
            recipe,
            change_note="Edycja receptury",
        )
        invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return recipe, version_created


@transaction.atomic
def delete_recipe(recipe) -> dict:
    farm = recipe.farm
    deleted_recipe = _deleted_recipe_data(recipe)
    recipe.delete()
    invalidate_farm_cache_on_commit(farm, groups=("feed",))
    return deleted_recipe
