from django.urls import reverse

from farms.module_registry import MODULE_DEFINITIONS, MODULE_GROUPS, MODULE_KEYS, default_nav_modules

MOBILE_NAV_KEYS = ("sows", "inventory", "sales")


def normalize_visible_modules(value) -> list[str]:
    selected = set(MODULE_KEYS if value is None else value)
    selected.add("settings")
    return [key for key in MODULE_KEYS if key in selected]


def normalize_nav_modules(value, *, visible_keys=None) -> list[str]:
    visible = set(normalize_visible_modules(visible_keys))
    selected = set(default_nav_modules() if value is None else value)
    selected.discard("settings")
    return [
        key
        for key in MODULE_KEYS
        if key in selected and key in visible and key != "settings"
    ]


class ModuleNavigationService:
    def __init__(self, farm, active_url_name=""):
        self.farm = farm
        self.active_url_name = active_url_name or ""

    def visible_keys(self) -> list[str]:
        if not self.farm:
            return ["settings"]
        from farms.services.settings_service import get_farm_settings

        return normalize_visible_modules(get_farm_settings(self.farm).visible_modules)

    def modules(self) -> list[dict]:
        visible = set(self.visible_keys())
        return [
            {
                **definition,
                "url": reverse(definition["url_name"]),
                "is_active": self.active_url_name in definition["active_urls"],
            }
            for definition in MODULE_DEFINITIONS
            if definition["key"] in visible
        ]

    def grouped_modules(self, modules: list[dict] | None = None) -> list[dict]:
        modules = modules if modules is not None else self.modules()
        grouped = []
        for group_key, title in MODULE_GROUPS:
            items = [module for module in modules if module["group"] == group_key and module["key"] != "settings"]
            if items:
                grouped.append({"key": group_key, "title": title, "modules": items})
        return grouped

    def primary_modules(self, modules: list[dict] | None = None) -> list[dict]:
        modules = modules if modules is not None else self.modules()
        settings = None
        if self.farm:
            from farms.services.settings_service import get_farm_settings

            settings = get_farm_settings(self.farm)
        selected_keys = normalize_nav_modules(
            getattr(settings, "nav_modules", None),
            visible_keys=getattr(settings, "visible_modules", None),
        )
        by_key = {module["key"]: module for module in modules if module["key"] != "settings"}
        return [by_key[key] for key in selected_keys if key in by_key]

    def mobile_modules(self, modules: list[dict] | None = None) -> list[dict]:
        modules = modules if modules is not None else self.modules()
        by_key = {module["key"]: module for module in modules if module["key"] != "settings"}
        mobile = [by_key[key] for key in MOBILE_NAV_KEYS if key in by_key]
        active = next((module for module in modules if module["is_active"] and module["key"] != "settings"), None)
        if active and active["key"] not in {module["key"] for module in mobile}:
            mobile = [active, *mobile]
        return mobile[:3]


def module_visibility_groups(form) -> list[dict]:
    definitions = {item["key"]: item for item in MODULE_DEFINITIONS}
    groups = []
    for group_key, title in MODULE_GROUPS:
        fields = []
        for key in MODULE_KEYS:
            if definitions[key]["group"] != group_key:
                continue
            field_name = f"show_{key}"
            if field_name in form.fields:
                fields.append({
                    "key": key,
                    "field": form[field_name],
                    "nav_field": form[f"nav_{key}"],
                    "description": definitions[key]["description"],
                })
        if group_key == "system":
            fields.append({"key": "settings", "field": None, "title": "Ustawienia", "description": definitions["settings"]["description"]})
        groups.append({"key": group_key, "title": title, "fields": fields})
    return groups
