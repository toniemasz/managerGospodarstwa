MODULE_GROUPS = (
    ("production", "Produkcja"),
    ("feed", "Pasza i magazyn"),
    ("finance", "Finanse"),
    ("system", "System"),
)


MODULE_DEFINITIONS = (
    {
        "key": "tasks",
        "title": "Zadania na dziś",
        "url_name": "task_center",
        "group": "production",
        "icon": "Z",
        "icon_name": "tasks",
        "tone": "green",
        "description": "Najważniejsze alerty produkcyjne, magazynowe i finansowe.",
        "active_urls": (
            "task_center",
            "complete_today_tasks",
        ),
        "catalog_links": (
            {
                "title": "Panel zadań",
                "url_name": "task_center",
                "icon_name": "tasks",
                "active_urls": (
                    "task_center",
                    "complete_today_tasks",
                ),
            },
        ),
    },
    {
        "key": "statistics",
        "title": "Statystyki",
        "url_name": "farm_statistics",
        "group": "production",
        "icon": "St",
        "icon_name": "statistics",
        "tone": "green",
        "description": "Globalne wskaźniki paszowe, sprzedażowe, magazynowe i finansowe.",
        "active_urls": (
            "farm_statistics",
        ),
        "catalog_links": (
            {
                "title": "Statystyki gospodarstwa",
                "url_name": "farm_statistics",
                "icon_name": "statistics",
                "active_urls": (
                    "farm_statistics",
                ),
            },
        ),
    },
    {
        "key": "sows",
        "title": "Maciory",
        "url_name": "dashboard",
        "group": "production",
        "icon": "M",
        "icon_name": "sow",
        "tone": "",
        "description": "Cykle rozrodcze, zdarzenia, szczepienia i statystyki stada.",
        "active_urls": (
            "dashboard",
            "sow_detail",
            "add_sow",
            "edit_sow",
            "add_event",
            "edit_event",
            "bulk_sow_events",
            "bulk_pregnancy_check",
            "bulk_vaccinate",
            "farrowing_panel",
            "general_statistics",
            "archived_sows",
            "mortality_list",
            "report_mortality",
            "vaccination_plans",
            "add_vaccination_plan",
            "edit_vaccination_plan",
        ),
        "catalog_links": (
            {
                "title": "Lista macior",
                "url_name": "dashboard",
                "icon_name": "sow",
                "active_urls": (
                    "dashboard",
                    "sow_detail",
                    "add_sow",
                    "edit_sow",
                    "add_event",
                    "edit_event",
                    "bulk_sow_events",
                    "bulk_pregnancy_check",
                    "farrowing_panel",
                ),
            },
            {
                "title": "Upadki",
                "url_name": "mortality_list",
                "icon_name": "warning",
                "active_urls": (
                    "mortality_list",
                    "report_mortality",
                ),
            },
            {
                "title": "Statystyki",
                "url_name": "general_statistics",
                "icon_name": "statistics",
                "active_urls": (
                    "general_statistics",
                ),
            },
            {
                "title": "Szczepienia",
                "url_name": "vaccination_plans",
                "icon_name": "health",
                "active_urls": (
                    "vaccination_plans",
                    "add_vaccination_plan",
                    "edit_vaccination_plan",
                    "bulk_vaccinate",
                ),
            },
            {
                "title": "Archiwum",
                "url_name": "archived_sows",
                "icon_name": "history",
                "active_urls": (
                    "archived_sows",
                ),
            },
        ),
    },
    {
        "key": "sales",
        "title": "Sprzedaż",
        "url_name": "sales_list",
        "group": "finance",
        "icon": "S",
        "icon_name": "sales",
        "tone": "green",
        "description": "Dokumenty sprzedaży, wagi i rozliczenia roczne.",
        "active_urls": (
            "sales_list",
            "add_sale",
            "edit_sale",
        ),
        "catalog_links": (
            {
                "title": "Rejestr sprzedaży",
                "url_name": "sales_list",
                "icon_name": "sales",
                "active_urls": (
                    "sales_list",
                    "edit_sale",
                ),
            },
            {
                "title": "Dodaj sprzedaż",
                "url_name": "add_sale",
                "icon_name": "add",
                "active_urls": (
                    "add_sale",
                ),
            },
        ),
    },
    {
        "key": "feed",
        "title": "Pasza",
        "url_name": "ingredient_list",
        "group": "feed",
        "icon": "P",
        "icon_name": "feed",
        "tone": "amber",
        "description": "Składniki paszowe, ceny i kalkulator receptur.",
        "active_urls": (
            "ingredient_list",
            "add_ingredient",
            "edit_ingredient",
            "feed_calculator",
        ),
        "catalog_links": (
            {
                "title": "Składniki",
                "url_name": "ingredient_list",
                "icon_name": "feed",
                "active_urls": (
                    "ingredient_list",
                    "add_ingredient",
                    "edit_ingredient",
                ),
            },
            {
                "title": "Kalkulator",
                "url_name": "feed_calculator",
                "icon_name": "calculator",
                "active_urls": (
                    "feed_calculator",
                ),
            },
        ),
    },
    {
        "key": "inventory",
        "title": "Magazyn",
        "url_name": "feed_inventory",
        "group": "feed",
        "icon": "Mg",
        "icon_name": "warehouse",
        "tone": "amber",
        "description": "Surowce, gotowe pasze, podania i ruchy magazynowe.",
        "active_urls": (
            "feed_inventory",
            "feed_full_inventory",
            "add_delivery",
            "edit_delivery",
            "inventory_adjustment",
            "finished_feed_inventory",
            "create_ready_feed_product",
            "add_ready_feed_delivery",
            "feed_servings",
            "create_feed_serving",
        ),
        "catalog_links": (
            {
                "title": "Magazyn",
                "url_name": "feed_inventory",
                "icon_name": "warehouse",
                "active_urls": (
                    "feed_inventory",
                    "add_delivery",
                    "edit_delivery",
                    "inventory_adjustment",
                ),
            },
            {
                "title": "Pełny magazyn",
                "url_name": "feed_full_inventory",
                "icon_name": "warehouse",
                "active_urls": (
                    "feed_full_inventory",
                ),
            },
            {
                "title": "Gotowe pasze",
                "url_name": "finished_feed_inventory",
                "icon_name": "feed",
                "active_urls": (
                    "finished_feed_inventory",
                    "create_ready_feed_product",
                    "add_ready_feed_delivery",
                ),
            },
            {
                "title": "Podania",
                "url_name": "feed_servings",
                "icon_name": "serving",
                "active_urls": (
                    "feed_servings",
                    "create_feed_serving",
                ),
            },
        ),
    },
    {
        "key": "recipes",
        "title": "Receptury",
        "url_name": "feed_recipes",
        "group": "feed",
        "icon": "R",
        "icon_name": "recipes",
        "tone": "amber",
        "description": "Skład mieszanek oraz rzeczywiste koszty receptur.",
        "active_urls": (
            "feed_recipes",
            "recipe_detail",
            "add_recipe",
            "edit_recipe",
            "recipe_version_detail",
            "edit_recipe_version",
            "add_recipe_version",
        ),
        "catalog_links": (
            {
                "title": "Lista receptur",
                "url_name": "feed_recipes",
                "icon_name": "recipes",
                "active_urls": (
                    "feed_recipes",
                    "recipe_detail",
                    "edit_recipe",
                    "recipe_version_detail",
                    "edit_recipe_version",
                    "add_recipe_version",
                ),
            },
            {
                "title": "Dodaj recepturę",
                "url_name": "add_recipe",
                "icon_name": "add",
                "active_urls": (
                    "add_recipe",
                ),
            },
        ),
    },
    {
        "key": "production",
        "title": "Śrutowanie",
        "url_name": "feed_productions",
        "group": "feed",
        "icon": "Ś",
        "icon_name": "production",
        "tone": "amber",
        "description": "Kolejka, etapy i zakończone produkcje paszy.",
        "active_urls": (
            "feed_productions",
            "add_production",
            "edit_production",
            "bulk_complete_productions",
            "process_stage1",
            "process_stage2",
        ),
        "catalog_links": (
            {
                "title": "Lista śrutowań",
                "url_name": "feed_productions",
                "icon_name": "production",
                "active_urls": (
                    "feed_productions",
                    "edit_production",
                    "bulk_complete_productions",
                    "process_stage1",
                    "process_stage2",
                ),
            },
            {
                "title": "Nowe śrutowanie",
                "url_name": "add_production",
                "icon_name": "add",
                "active_urls": (
                    "add_production",
                ),
            },
        ),
    },
    {
        "key": "costs",
        "title": "Koszty",
        "url_name": "cost_list",
        "group": "finance",
        "icon": "K",
        "icon_name": "costs",
        "tone": "green",
        "description": "Dokumenty kosztowe, kategorie i statusy płatności.",
        "active_urls": (
            "cost_list",
            "add_cost",
            "edit_cost",
            "cost_categories",
            "add_cost_category",
            "edit_cost_category",
            "deactivate_cost_category",
        ),
        "catalog_links": (
            {
                "title": "Rejestr kosztów",
                "url_name": "cost_list",
                "icon_name": "costs",
                "active_urls": (
                    "cost_list",
                    "add_cost",
                    "edit_cost",
                ),
            },
            {
                "title": "Kategorie",
                "url_name": "cost_categories",
                "icon_name": "categories",
                "active_urls": (
                    "cost_categories",
                    "add_cost_category",
                    "edit_cost_category",
                    "deactivate_cost_category",
                ),
            },
        ),
    },
    {
        "key": "finance",
        "title": "Opłacalność",
        "url_name": "profitability",
        "group": "finance",
        "icon": "F",
        "icon_name": "finance",
        "tone": "green",
        "description": "Sprzedaż, rzeczywisty koszt paszy i wynik roczny.",
        "active_urls": (
            "profitability",
        ),
        "catalog_links": (
            {
                "title": "Analiza opłacalności",
                "url_name": "profitability",
                "icon_name": "finance",
                "active_urls": (
                    "profitability",
                ),
            },
        ),
    },
    {
        "key": "audit",
        "title": "Historia zmian",
        "url_name": "audit_log",
        "group": "system",
        "icon": "H",
        "icon_name": "history",
        "tone": "",
        "description": "Rejestr najważniejszych operacji gospodarstwa.",
        "active_urls": (
            "audit_log",
        ),
        "catalog_links": (
            {
                "title": "Historia zmian",
                "url_name": "audit_log",
                "icon_name": "history",
                "active_urls": (
                    "audit_log",
                ),
            },
        ),
    },
    {
        "key": "settings",
        "title": "Ustawienia",
        "url_name": "farm_settings",
        "group": "system",
        "icon": "U",
        "icon_name": "settings",
        "tone": "",
        "description": "Reguły gospodarstwa, widoczność modułów i eksport danych.",
        "active_urls": (
            "farm_settings",
            "export_user_data",
            "export_csv",
        ),
        "catalog_links": (
            {
                "title": "Ustawienia",
                "url_name": "farm_settings",
                "icon_name": "settings",
                "active_urls": (
                    "farm_settings",
                    "export_user_data",
                    "export_csv",
                ),
            },
        ),
    },
)


MODULE_KEYS = tuple(
    module["key"]
    for module in MODULE_DEFINITIONS
)


def default_visible_modules():
    return list(MODULE_KEYS)


def default_nav_modules():
    return [
        "tasks",
        "statistics",
        "sows",
        "feed",
        "sales",
    ]