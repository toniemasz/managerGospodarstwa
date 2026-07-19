from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from common.cache import invalidate_farm_cache_on_commit
from sows.models import SowModel


class SowEarTagConflictError(ValidationError):
    pass


@transaction.atomic
def save_sow(*, farm, form) -> SowModel:
    """Zapisuje maciorę i chroni aktywny numer kolczyka w gospodarstwie."""

    sow = form.save(commit=False)
    if sow.farm_id and sow.farm_id != farm.id:
        raise ValidationError("Maciora nie należy do wskazanego gospodarstwa.")

    farm.__class__.objects.select_for_update().get(pk=farm.pk)
    sow.farm = farm
    sow.ear_tag = sow.ear_tag.strip()
    try:
        with transaction.atomic():
            sow.save()
    except IntegrityError as error:
        constraint_name = getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)
        if constraint_name == "unique_active_sow_ear_tag_per_farm_ci":
            raise SowEarTagConflictError(
                "Aktywna maciora o tym numerze kolczyka już istnieje w tym gospodarstwie."
            ) from error
        raise

    invalidate_farm_cache_on_commit(farm, groups=("sows",))
    return sow
