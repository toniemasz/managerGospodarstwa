MODULE_GROUPS = (
    ("production", "Produkcja"),
    ("feed", "Pasza i magazyn"),
    ("finance", "Finanse"),
    ("system", "System"),
)

MODULE_DEFINITIONS = (
    {"key": "tasks", "title": "Zadania", "url_name": "task_center", "group": "production", "icon": "Z", "tone": "green", "description": "Najważniejsze alerty produkcyjne, magazynowe i finansowe.", "active_urls": ("task_center",)},
    {"key": "sows", "title": "Maciory", "url_name": "dashboard", "group": "production", "icon": "M", "tone": "", "description": "Cykle rozrodcze, zdarzenia, szczepienia i statystyki stada.", "active_urls": ("dashboard", "sow_detail", "add_sow", "edit_sow", "add_event", "edit_event", "bulk_sow_events", "bulk_pregnancy_check", "bulk_vaccinate", "farrowing_panel", "general_statistics", "archived_sows", "vaccination_plans", "add_vaccination_plan", "edit_vaccination_plan")},
    {"key": "sales", "title": "Sprzedaż", "url_name": "sales_list", "group": "finance", "icon": "S", "tone": "green", "description": "Dokumenty sprzedaży, wagi i rozliczenia roczne.", "active_urls": ("sales_list", "add_sale", "edit_sale")},
    {"key": "feed", "title": "Pasza", "url_name": "ingredient_list", "group": "feed", "icon": "P", "tone": "amber", "description": "Składniki paszowe, ceny i kalkulator receptur.", "active_urls": ("ingredient_list", "add_ingredient", "edit_ingredient", "feed_calculator")},
    {"key": "inventory", "title": "Magazyn", "url_name": "feed_inventory", "group": "feed", "icon": "Mg", "tone": "amber", "description": "Dostawy, ruchy, korekty i bieżące stany surowców.", "active_urls": ("feed_inventory", "feed_full_inventory", "add_delivery", "edit_delivery", "inventory_adjustment")},
    {"key": "recipes", "title": "Receptury", "url_name": "feed_recipes", "group": "feed", "icon": "R", "tone": "amber", "description": "Skład mieszanek oraz rzeczywiste koszty receptur.", "active_urls": ("feed_recipes", "recipe_detail", "add_recipe", "edit_recipe")},
    {"key": "production", "title": "Śrutowanie", "url_name": "feed_productions", "group": "feed", "icon": "Ś", "tone": "amber", "description": "Kolejka, etapy i zakończone produkcje paszy.", "active_urls": ("feed_productions", "add_production", "edit_production", "process_stage1", "process_stage2")},
    {"key": "costs", "title": "Koszty", "url_name": "cost_list", "group": "finance", "icon": "K", "tone": "green", "description": "Dokumenty kosztowe, kategorie i statusy płatności.", "active_urls": ("cost_list", "add_cost", "edit_cost", "cost_categories", "add_cost_category", "edit_cost_category")},
    {"key": "finance", "title": "Opłacalność", "url_name": "profitability", "group": "finance", "icon": "F", "tone": "green", "description": "Sprzedaż, rzeczywisty koszt paszy i wynik roczny.", "active_urls": ("profitability",)},
    {"key": "audit", "title": "Historia zmian", "url_name": "audit_log", "group": "system", "icon": "H", "tone": "", "description": "Rejestr najważniejszych operacji gospodarstwa.", "active_urls": ("audit_log",)},
    {"key": "settings", "title": "Ustawienia", "url_name": "farm_settings", "group": "system", "icon": "U", "tone": "", "description": "Reguły gospodarstwa, widoczność modułów i eksport danych.", "active_urls": ("farm_settings", "export_user_data", "export_csv")},
)

MODULE_KEYS = tuple(item["key"] for item in MODULE_DEFINITIONS)


def default_visible_modules():
    return list(MODULE_KEYS)


def default_nav_modules():
    return ["tasks", "sows", "feed", "sales"]
