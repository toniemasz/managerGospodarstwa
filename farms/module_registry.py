MODULE_GROUPS = (
    ("production", "Produkcja"),
    ("feed", "Pasza i magazyn"),
    ("finance", "Finanse"),
    ("system", "System"),
)

MODULE_DEFINITIONS = (
    {"key": "tasks", "title": "Zadania na dziś", "url_name": "task_center", "group": "production", "icon": "Z", "icon_name": "tasks", "tone": "green", "description": "Najważniejsze alerty produkcyjne, magazynowe i finansowe.", "active_urls": ("task_center", "complete_today_tasks")},
    {"key": "statistics", "title": "Statystyki", "url_name": "farm_statistics", "group": "production", "icon": "St", "icon_name": "statistics", "tone": "green", "description": "Globalne wskaźniki paszowe, sprzedażowe, magazynowe i finansowe.", "active_urls": ("farm_statistics",)},
    {"key": "sows", "title": "Maciory", "url_name": "dashboard", "group": "production", "icon": "M", "icon_name": "sow", "tone": "", "description": "Cykle rozrodcze, zdarzenia, szczepienia i statystyki stada.", "active_urls": ("dashboard", "sow_detail", "add_sow", "edit_sow", "add_event", "edit_event", "bulk_sow_events", "bulk_pregnancy_check", "bulk_vaccinate", "farrowing_panel", "general_statistics", "archived_sows", "mortality_list", "report_mortality", "vaccination_plans", "add_vaccination_plan", "edit_vaccination_plan")},
    {"key": "sales", "title": "Sprzedaż", "url_name": "sales_list", "group": "finance", "icon": "S", "icon_name": "sales", "tone": "green", "description": "Dokumenty sprzedaży, wagi i rozliczenia roczne.", "active_urls": ("sales_list", "add_sale", "edit_sale")},
    {"key": "feed", "title": "Pasza", "url_name": "ingredient_list", "group": "feed", "icon": "P", "icon_name": "feed", "tone": "amber", "description": "Składniki paszowe, ceny i kalkulator receptur.", "active_urls": ("ingredient_list", "add_ingredient", "edit_ingredient", "feed_calculator")},
    {"key": "inventory", "title": "Magazyn", "url_name": "feed_inventory", "group": "feed", "icon": "Mg", "icon_name": "warehouse", "tone": "amber", "description": "Dostawy, ruchy, korekty i bieżące stany surowców.", "active_urls": ("feed_inventory", "feed_full_inventory", "add_delivery", "edit_delivery", "inventory_adjustment")},
    {"key": "recipes", "title": "Receptury", "url_name": "feed_recipes", "group": "feed", "icon": "R", "icon_name": "recipes", "tone": "amber", "description": "Skład mieszanek oraz rzeczywiste koszty receptur.", "active_urls": ("feed_recipes", "recipe_detail", "add_recipe", "edit_recipe")},
    {"key": "production", "title": "Śrutowanie", "url_name": "feed_productions", "group": "feed", "icon": "Ś", "icon_name": "production", "tone": "amber", "description": "Kolejka, etapy i zakończone produkcje paszy.", "active_urls": ("feed_productions", "add_production", "edit_production", "process_stage1", "process_stage2")},
    {"key": "costs", "title": "Koszty", "url_name": "cost_list", "group": "finance", "icon": "K", "icon_name": "costs", "tone": "green", "description": "Dokumenty kosztowe, kategorie i statusy płatności.", "active_urls": ("cost_list", "add_cost", "edit_cost", "cost_categories", "add_cost_category", "edit_cost_category")},
    {"key": "finance", "title": "Opłacalność", "url_name": "profitability", "group": "finance", "icon": "F", "icon_name": "finance", "tone": "green", "description": "Sprzedaż, rzeczywisty koszt paszy i wynik roczny.", "active_urls": ("profitability",)},
    {"key": "audit", "title": "Historia zmian", "url_name": "audit_log", "group": "system", "icon": "H", "icon_name": "history", "tone": "", "description": "Rejestr najważniejszych operacji gospodarstwa.", "active_urls": ("audit_log",)},
    {"key": "settings", "title": "Ustawienia", "url_name": "farm_settings", "group": "system", "icon": "U", "icon_name": "settings", "tone": "", "description": "Reguły gospodarstwa, widoczność modułów i eksport danych.", "active_urls": ("farm_settings", "export_user_data", "export_csv")},
)

MODULE_KEYS = tuple(item["key"] for item in MODULE_DEFINITIONS)


def default_visible_modules():
    return list(MODULE_KEYS)


def default_nav_modules():
    return ["tasks", "statistics", "sows", "feed", "sales"]
