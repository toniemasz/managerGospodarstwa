from farms.dashboard_registry import DASHBOARD_STAT_DEFINITIONS
from farms.module_registry import MODULE_DEFINITIONS


def dashboard_stat_groups(form) -> list[dict]:
    """Grupuje konfigurowalne statystyki dashboardu dla formularza ustawień."""

    module_titles = {module["key"]: module["title"] for module in MODULE_DEFINITIONS}
    groups = []
    for module_key in (
        "tasks",
        "sows",
        "inventory",
        "production",
        "sales",
        "costs",
        "finance",
    ):
        stats = []
        for stat in DASHBOARD_STAT_DEFINITIONS:
            field_name = f"stat_{stat['key']}"
            if stat["module"] == module_key and field_name in form.fields:
                stats.append(
                    {
                        "key": stat["key"],
                        "field": form[field_name],
                        "description": stat["description"],
                        "icon_name": stat["icon_name"],
                        "tone": stat["tone"],
                    }
                )
        if stats:
            groups.append(
                {
                    "key": module_key,
                    "title": module_titles.get(module_key, module_key),
                    "stats": stats,
                }
            )
    return groups
