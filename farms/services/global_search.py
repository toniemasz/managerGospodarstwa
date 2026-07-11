from __future__ import annotations

from django.urls import reverse

from costs.search import search_cost_categories, search_costs
from farms.services.module_navigation import ModuleNavigationService
from feed.services.search import FeedSearchProvider
from sales.search import search_sales
from sows.services.search import search_sows, search_vaccination_plans
from common.units import format_mass


MIN_SEARCH_LENGTH = 2
MAX_RESULTS_PER_GROUP = 8


def build_global_search_context(farm, query: str, *, active_url_name: str = "global_search") -> dict:
    search_term = (query or "").strip()
    groups = []
    if len(search_term) >= MIN_SEARCH_LENGTH:
        collectors = (
            _module_results,
            _sow_results,
            _feed_results,
            _production_results,
            _sales_results,
            _cost_results,
        )
        groups = [
            group
            for collector in collectors
            for group in (collector(farm, search_term, active_url_name),)
            if group["items"]
        ]
    total_count = sum(len(group["items"]) for group in groups)
    return {
        "global_search_query": search_term,
        "search_groups": groups,
        "search_total_count": total_count,
        "search_min_length": MIN_SEARCH_LENGTH,
        "search_is_short": bool(search_term) and len(search_term) < MIN_SEARCH_LENGTH,
        "search_has_query": bool(search_term),
    }


def _contains(value: str, query: str) -> bool:
    return query.casefold() in value.casefold()


def _group(key: str, title: str, icon_name: str, items: list[dict]) -> dict:
    return {
        "key": key,
        "title": title,
        "icon_name": icon_name,
        "items": items,
    }


def _module_results(farm, query: str, active_url_name: str) -> dict:
    service = ModuleNavigationService(farm, active_url_name)
    items = []
    for module in service.all_modules():
        haystack = f"{module['title']} {module['description']}"
        if _contains(haystack, query):
            items.append({
                "title": module["title"],
                "subtitle": module["description"],
                "meta": "Moduł widoczny" if module["is_visible"] else "Ukryty w ustawieniach",
                "url": module["url"] if module["is_visible"] else reverse("farm_settings") + "#settings-modules",
                "icon_name": module["icon_name"],
                "tone": module["tone"],
            })
    return _group("modules", "Moduły", "dashboard", items[:MAX_RESULTS_PER_GROUP])


def _sow_results(farm, query: str, active_url_name: str) -> dict:
    items = [
        {
            "title": f"Maciora {sow.ear_tag}",
            "subtitle": "Archiwum" if sow.is_archived else "Aktywna karta maciory",
            "meta": f"Wpis od {sow.entry_date:%d.%m.%Y}",
            "url": reverse("sow_detail", args=[sow.id]),
            "icon_name": "sow",
            "tone": "green",
        }
        for sow in search_sows(farm, query, limit=MAX_RESULTS_PER_GROUP)
    ]
    plans = [
        {
            "title": plan.name,
            "subtitle": "Plan szczepienia",
            "meta": "Konfiguracja rozrodu",
            "url": reverse("edit_vaccination_plan", args=[plan.id]),
            "icon_name": "health",
            "tone": "green",
        }
        for plan in search_vaccination_plans(farm, query, limit=MAX_RESULTS_PER_GROUP)
    ]
    return _group("sows", "Maciory i rozrod", "sow", (items + plans)[:MAX_RESULTS_PER_GROUP])


def _feed_results(farm, query: str, active_url_name: str) -> dict:
    provider = FeedSearchProvider(farm)
    ingredients = [
        {
            "title": ingredient.name,
            "subtitle": ingredient.description or "Składnik paszowy",
            "meta": "Magazyn",
            "url": reverse("edit_ingredient", args=[ingredient.id]),
            "icon_name": "feed",
            "tone": "amber",
        }
        for ingredient in provider.ingredients(query, limit=MAX_RESULTS_PER_GROUP)
    ]
    recipes = [
        {
            "title": recipe.name,
            "subtitle": "Receptura paszowa",
            "meta": f"Utworzono {recipe.created_at:%d.%m.%Y}",
            "url": reverse("recipe_detail", args=[recipe.id]),
            "icon_name": "recipes",
            "tone": "amber",
        }
        for recipe in provider.recipes(query, limit=MAX_RESULTS_PER_GROUP)
    ]
    return _group("feed", "Pasza i magazyn", "feed", (ingredients + recipes)[:MAX_RESULTS_PER_GROUP])


def _production_results(farm, query: str, active_url_name: str) -> dict:
    items = [
        {
            "title": f"Śrutowanie: {production.recipe.name}",
            "subtitle": f"{format_mass(production.quantity_kg)} paszy",
            "meta": f"{production.status_label} • {production.date:%d.%m.%Y}",
            "url": reverse("edit_production", args=[production.id]),
            "icon_name": "production",
            "tone": "amber",
        }
        for production in FeedSearchProvider(farm).productions(query, limit=MAX_RESULTS_PER_GROUP)
    ]
    return _group("production", "Śrutowanie", "production", items)


def _sales_results(farm, query: str, active_url_name: str) -> dict:
    items = [
        {
            "title": sale.document_number or f"Sprzedaż {_date_label(sale.sale_date)}",
            "subtitle": f"{sale.quantity} szt. • {sale.net_value:.2f} PLN netto",
            "meta": sale.tattoo or "Brak tatuażu",
            "url": reverse("edit_sale", args=[sale.id]),
            "icon_name": "sales",
            "tone": "green",
        }
        for sale in search_sales(farm, query, limit=MAX_RESULTS_PER_GROUP)
    ]
    return _group("sales", "Sprzedaż", "sales", items)


def _cost_results(farm, query: str, active_url_name: str) -> dict:
    costs = [
        {
            "title": cost.description,
            "subtitle": f"{cost.amount:.2f} PLN • {cost.date:%d.%m.%Y}",
            "meta": "Opłacony" if cost.is_paid else "Nieopłacony",
            "url": reverse("edit_cost", args=[cost.id]),
            "icon_name": "costs",
            "tone": "green" if cost.is_paid else "warning",
        }
        for cost in search_costs(farm, query, limit=MAX_RESULTS_PER_GROUP)
    ]
    categories = [
        {
            "title": category.name,
            "subtitle": category.description or "Kategoria kosztów",
            "meta": "Aktywna" if category.is_active else "Nieaktywna",
            "url": reverse("edit_cost_category", args=[category.id]),
            "icon_name": "costs",
            "tone": "green",
        }
        for category in search_cost_categories(farm, query, limit=MAX_RESULTS_PER_GROUP)
    ]
    return _group("costs", "Koszty", "costs", (costs + categories)[:MAX_RESULTS_PER_GROUP])


def _date_label(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "bez daty"
