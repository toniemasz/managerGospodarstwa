from django.urls import reverse

from farms.module_registry import (
    MODULE_DEFINITIONS,
    MODULE_GROUPS,
    MODULE_KEYS,
    default_nav_modules,
)


MOBILE_NAV_KEYS = (
    "tasks",
    "sows",
    "inventory",
)


def normalize_visible_modules(value) -> list[str]:
    selected = set(MODULE_KEYS if value is None else value)

    # Ustawienia muszą pozostać zawsze dostępne.
    selected.add("settings")

    return [
        key
        for key in MODULE_KEYS
        if key in selected
    ]


def normalize_nav_modules(value, *, visible_keys=None) -> list[str]:
    visible = set(normalize_visible_modules(visible_keys))
    selected = set(
        default_nav_modules()
        if value is None
        else value
    )

    # Ustawienia mają własne stałe miejsce i nie mogą być przypinane.
    selected.discard("settings")

    return [
        key
        for key in MODULE_KEYS
        if (
            key in selected
            and key in visible
            and key != "settings"
        )
    ]


class ModuleNavigationService:
    def __init__(self, farm, active_url_name=""):
        self.farm = farm
        self.active_url_name = active_url_name or ""

    def _settings(self):
        if not self.farm:
            return None

        from farms.services.settings_service import get_farm_settings

        return get_farm_settings(self.farm)

    def visible_keys(self) -> list[str]:
        settings = self._settings()

        if settings is None:
            return ["settings"]

        return normalize_visible_modules(
            settings.visible_modules
        )

    def nav_keys(self) -> list[str]:
        """
        Zwraca moduły przypięte do głównego paska nawigacji.

        Korzysta z tego samego pola nav_modules, które jest obsługiwane
        przez formularz ustawień gospodarstwa.
        """
        settings = self._settings()

        if settings is None:
            return []

        return normalize_nav_modules(
            settings.nav_modules,
            visible_keys=settings.visible_modules,
        )

    def _build_module(
        self,
        definition: dict,
        *,
        visible_keys: set[str],
        pinned_keys: set[str],
        include_visibility: bool,
    ) -> dict:
        module = {
            **{
                key: value
                for key, value in definition.items()
                if key != "catalog_links"
            },
            "url": reverse(definition["url_name"]),
            "is_active": (
                self.active_url_name
                in definition["active_urls"]
            ),
            "is_pinned": (
                definition["key"] in pinned_keys
            ),
        }

        if include_visibility:
            module["is_visible"] = (
                definition["key"] in visible_keys
            )

        return module

    def modules(self) -> list[dict]:
        """
        Zwraca wyłącznie moduły dostępne w gospodarstwie.

        Ta lista jest używana między innymi przez główną
        i mobilną nawigację.
        """
        visible = set(self.visible_keys())
        pinned = set(self.nav_keys())

        return [
            self._build_module(
                definition,
                visible_keys=visible,
                pinned_keys=pinned,
                include_visibility=False,
            )
            for definition in MODULE_DEFINITIONS
            if definition["key"] in visible
        ]

    def all_modules(self) -> list[dict]:
        """
        Zwraca pełny katalog modułów, również tych ukrytych.

        Każdy moduł zawiera:
        - is_visible — czy jest dostępny w gospodarstwie,
        - is_pinned — czy jest przypięty do paska,
        """
        visible = set(self.visible_keys())
        pinned = set(self.nav_keys())

        return [
            self._build_module(
                definition,
                visible_keys=visible,
                pinned_keys=pinned,
                include_visibility=True,
            )
            for definition in MODULE_DEFINITIONS
        ]

    def grouped_modules(
        self,
        modules: list[dict] | None = None,
        *,
        include_settings=False,
    ) -> list[dict]:
        modules = (
            modules
            if modules is not None
            else self.modules()
        )

        grouped = []

        for group_key, title in MODULE_GROUPS:
            items = [
                module
                for module in modules
                if (
                    module["group"] == group_key
                    and (
                        include_settings
                        or module["key"] != "settings"
                    )
                )
            ]

            if items:
                grouped.append(
                    {
                        "key": group_key,
                        "title": title,
                        "modules": items,
                    }
                )

        return grouped

    def primary_modules(
        self,
        modules: list[dict] | None = None,
    ) -> list[dict]:
        modules = (
            modules
            if modules is not None
            else self.modules()
        )

        selected_keys = self.nav_keys()

        by_key = {
            module["key"]: module
            for module in modules
            if module["key"] != "settings"
        }

        return [
            by_key[key]
            for key in selected_keys
            if key in by_key
        ]

    def mobile_modules(
        self,
        modules: list[dict] | None = None,
    ) -> list[dict]:
        modules = (
            modules
            if modules is not None
            else self.modules()
        )

        by_key = {
            module["key"]: module
            for module in modules
            if module["key"] != "settings"
        }

        mobile = [
            by_key[key]
            for key in MOBILE_NAV_KEYS
            if key in by_key
        ]

        active = next(
            (
                module
                for module in modules
                if (
                    module["is_active"]
                    and module["key"] != "settings"
                )
            ),
            None,
        )

        mobile_keys = {
            module["key"]
            for module in mobile
        }

        if active and active["key"] not in mobile_keys:
            mobile = [
                active,
                *mobile,
            ]

        return mobile[:3]


def module_visibility_groups(form) -> list[dict]:
    definitions = {
        item["key"]: item
        for item in MODULE_DEFINITIONS
    }

    groups = []

    for group_key, title in MODULE_GROUPS:
        fields = []

        for key in MODULE_KEYS:
            if definitions[key]["group"] != group_key:
                continue

            field_name = f"show_{key}"

            if field_name in form.fields:
                fields.append(
                    {
                        "key": key,
                        "field": form[field_name],
                        "nav_field": form[f"nav_{key}"],
                        "description": definitions[key]["description"],
                        "icon_name": definitions[key]["icon_name"],
                        "tone": definitions[key]["tone"],
                    }
                )

        if group_key == "system":
            fields.append(
                {
                    "key": "settings",
                    "field": None,
                    "title": "Ustawienia",
                    "description": definitions["settings"]["description"],
                    "icon_name": definitions["settings"]["icon_name"],
                    "tone": definitions["settings"]["tone"],
                }
            )

        groups.append(
            {
                "key": group_key,
                "title": title,
                "fields": fields,
            }
        )

    return groups
