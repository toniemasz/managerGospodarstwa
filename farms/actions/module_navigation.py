from django.core.exceptions import ValidationError
from django.db import transaction

from farms.module_registry import MODULE_KEYS
from farms.services.module_navigation import (
    normalize_nav_modules,
    normalize_visible_modules,
)
from farms.services.settings_service import get_farm_settings


@transaction.atomic
def set_module_pinned(
    *,
    farm,
    module_key: str,
    is_pinned: bool,
):
    """
    Przypina albo odpina moduł od głównego paska nawigacji gospodarstwa.
    """

    if module_key == "settings":
        raise ValidationError(
            "Ustawień nie można przypiąć do głównego paska nawigacji."
        )

    if module_key not in MODULE_KEYS:
        raise ValidationError(
            "Wybrany moduł nie istnieje."
        )

    settings = get_farm_settings(farm)

    visible_modules = normalize_visible_modules(
        settings.visible_modules
    )

    if module_key not in visible_modules:
        raise ValidationError(
            "Ukrytego modułu nie można przypiąć do paska nawigacji."
        )

    current_nav_modules = set(
        normalize_nav_modules(
            settings.nav_modules,
            visible_keys=visible_modules,
        )
    )

    if is_pinned:
        current_nav_modules.add(module_key)
    else:
        current_nav_modules.discard(module_key)

    settings.nav_modules = normalize_nav_modules(
        current_nav_modules,
        visible_keys=visible_modules,
    )

    settings.save(
        update_fields=[
            "nav_modules",
        ]
    )

    return settings