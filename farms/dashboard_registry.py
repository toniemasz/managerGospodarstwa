from farms.module_registry import MODULE_KEYS


DASHBOARD_STAT_DEFINITIONS = (
    {"key": "tasks_total", "module": "tasks", "title": "Zadania na dziś", "description": "Łączna liczba aktywnych zadań z centrali.", "icon_name": "tasks", "tone": "neutral", "default_visible": True},
    {"key": "total_sows", "module": "sows", "title": "Maciory", "description": "Wszystkie aktywne maciory w gospodarstwie.", "icon_name": "sow", "tone": "green", "default_visible": True},
    {"key": "pregnant_sows", "module": "sows", "title": "W ciąży", "description": "Maciory sklasyfikowane jako prośne.", "icon_name": "sow", "tone": "green", "default_visible": False},
    {"key": "farrowing_due", "module": "sows", "title": "Oproszenia", "description": "Oproszenia w najbliższym oknie alertów.", "icon_name": "calendar", "tone": "warning", "default_visible": False},
    {"key": "vaccinations_due", "module": "sows", "title": "Szczepienia", "description": "Szczepienia wymagające potwierdzenia.", "icon_name": "health", "tone": "neutral", "default_visible": False},
    {"key": "low_stock", "module": "inventory", "title": "Niski stan", "description": "Składniki poniżej ustawionego progu magazynowego.", "icon_name": "warning", "tone": "danger", "default_visible": True},
    {"key": "inventory_total", "module": "inventory", "title": "Magazyn", "description": "Łączny stan surowców paszowych.", "icon_name": "warehouse", "tone": "green", "default_visible": False},
    {"key": "queued_productions", "module": "production", "title": "Śrutowania", "description": "Produkcje paszy oczekujące w kolejce.", "icon_name": "production", "tone": "neutral", "default_visible": False},
    {"key": "pending_sales", "module": "sales", "title": "Sprzedaże", "description": "Sprzedaże oznaczone jako bez rozliczenia.", "icon_name": "sales", "tone": "green", "default_visible": True},
    {"key": "unpaid_costs", "module": "costs", "title": "Koszty", "description": "Koszty nieoznaczone jako opłacone.", "icon_name": "costs", "tone": "warning", "default_visible": False},
    {"key": "net_result", "module": "finance", "title": "Wynik netto", "description": "Bieżący wynik netto z modułu opłacalności.", "icon_name": "finance", "tone": "green", "default_visible": False},
)

DASHBOARD_STAT_KEYS = tuple(item["key"] for item in DASHBOARD_STAT_DEFINITIONS)


def default_dashboard_stats():
    return [item["key"] for item in DASHBOARD_STAT_DEFINITIONS if item["default_visible"]]


def normalize_dashboard_stats(value, *, visible_keys=None) -> list[str]:
    visible = set(MODULE_KEYS if visible_keys is None else visible_keys)
    selected = set(default_dashboard_stats() if value is None else value)
    return [
        item["key"]
        for item in DASHBOARD_STAT_DEFINITIONS
        if item["key"] in selected and item["module"] in visible
    ]
