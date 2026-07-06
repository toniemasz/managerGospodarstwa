from django.db import transaction

from feed.actions.recipe_versions import RecipeVersionActions


def create_recipe(form, formset, *, farm, user=None):
    with transaction.atomic():
        recipe = form.save(commit=False)
        recipe.farm = farm
        recipe.save()
        formset.instance = recipe
        formset.save()
        RecipeVersionActions(farm=farm, user=user).ensure_current_version(
            recipe,
            change_note="Utworzenie receptury",
        )
    return recipe


def update_recipe(form, formset, *, farm, user=None):
    with transaction.atomic():
        recipe = form.save()
        formset.save()
        _, version_created = RecipeVersionActions(farm=farm, user=user).ensure_current_version(
            recipe,
            change_note="Edycja receptury",
        )
    return recipe, version_created
