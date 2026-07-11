from __future__ import annotations

import copy
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)

CACHE_SCHEMA_VERSION = "v1"
TASK_CENTER_TTL = 60
TOPBAR_NOTIFICATIONS_TTL = 45
DASHBOARD_TTL = 120
TODAY_DASHBOARD_TTL = 60
INVENTORY_TTL = 300
PROFITABILITY_TTL = 900
STATISTICS_TTL = 900

ALL_FARM_CACHE_GROUPS = (
    "task_center", "topbar_notifications", "dashboard", "today_dashboard",
    "inventory", "profitability", "statistics", "navigation",
)

GROUP_DEPENDENCIES = {
    "task_center": ("task_center", "topbar_notifications", "dashboard", "today_dashboard"),
    "dashboard": ("dashboard", "today_dashboard", "topbar_notifications"),
    "today_dashboard": ("today_dashboard",),
    "inventory": ("inventory", "task_center", "topbar_notifications", "dashboard", "today_dashboard", "profitability", "statistics"),
    "profitability": ("profitability", "statistics", "dashboard", "today_dashboard"),
    "statistics": ("statistics", "profitability", "dashboard", "today_dashboard"),
    "navigation": ("navigation", "dashboard", "today_dashboard", "topbar_notifications"),
    "settings": ALL_FARM_CACHE_GROUPS,
    "sows": ("task_center", "topbar_notifications", "dashboard", "today_dashboard", "statistics"),
    "feed": ("inventory", "task_center", "topbar_notifications", "dashboard", "today_dashboard", "profitability", "statistics"),
    "sales": ("task_center", "topbar_notifications", "dashboard", "today_dashboard", "profitability", "statistics"),
    "costs": ("task_center", "topbar_notifications", "dashboard", "today_dashboard", "profitability", "statistics"),
}

_MISSING = object()


def farm_cache_key(farm, group: str, *parts: Any) -> str:
    farm_id = _farm_id(farm)
    if farm_id is None:
        raise ValueError("Farm cache key requires farm_id.")
    group_version = _group_version(farm_id, group)
    normalized_parts = ":".join(_normalize_cache_part(part) for part in parts)
    suffix = f":{normalized_parts}" if normalized_parts else ""
    return f"{CACHE_SCHEMA_VERSION}:farm:{farm_id}:{group}:gv:{group_version}{suffix}"


def cached_farm_value(farm, group: str, parts: Iterable[Any], *, timeout: int, builder: Callable[[], Any]):
    if _farm_id(farm) is None:
        return builder()
    key = farm_cache_key(farm, group, *parts)
    cached = safe_cache_get(key, _MISSING)
    if cached is not _MISSING:
        return _clone_cache_value(cached)
    value = builder()
    safe_cache_set(key, _clone_cache_value(value), timeout=timeout)
    return _clone_cache_value(value)


def invalidate_farm_cache(farm, groups: Iterable[str] | None = None) -> None:
    farm_id = _farm_id(farm)
    if farm_id is None:
        return
    version = str(time.time_ns())
    for group in _expand_groups(groups):
        safe_cache_set(_group_version_key(farm_id, group), version, timeout=None)


def invalidate_farm_cache_on_commit(farm, groups: Iterable[str] | None = None) -> None:
    transaction.on_commit(lambda: invalidate_farm_cache(farm, groups=groups))


def invalidate_inventory_cache(farm) -> None:
    invalidate_farm_cache(farm, groups=("inventory",))


def invalidate_dashboard_cache(farm) -> None:
    invalidate_farm_cache(farm, groups=("dashboard",))


def invalidate_task_cache(farm) -> None:
    invalidate_farm_cache(farm, groups=("task_center",))


def invalidate_profitability_cache(farm) -> None:
    invalidate_farm_cache(farm, groups=("profitability",))


def invalidate_statistics_cache(farm) -> None:
    invalidate_farm_cache(farm, groups=("statistics",))


def safe_cache_get(key: str, default=None):
    try:
        return cache.get(key, default)
    except Exception:
        logger.warning("Cache get failed for key %s", key, exc_info=True)
        return default


def safe_cache_set(key: str, value, *, timeout: int | None) -> bool:
    try:
        return cache.set(key, value, timeout=timeout)
    except Exception:
        logger.warning("Cache set failed for key %s", key, exc_info=True)
        return False


def safe_cache_delete_many(keys: Iterable[str]) -> None:
    keys = list(keys)
    if not keys:
        return
    try:
        cache.delete_many(keys)
    except Exception:
        logger.warning("Cache delete_many failed for %d keys", len(keys), exc_info=True)


def _farm_id(farm) -> int | None:
    if farm is None:
        return None
    return getattr(farm, "pk", farm)


def _group_version(farm_id: int, group: str) -> str:
    return str(safe_cache_get(_group_version_key(farm_id, group), "1"))


def _group_version_key(farm_id: int, group: str) -> str:
    return f"{CACHE_SCHEMA_VERSION}:farm:{farm_id}:cache-version:{group}"


def _expand_groups(groups: Iterable[str] | None) -> tuple[str, ...]:
    if groups is None:
        return ALL_FARM_CACHE_GROUPS
    expanded = []
    for group in groups:
        for resolved in GROUP_DEPENDENCIES.get(group, (group,)):
            if resolved not in expanded:
                expanded.append(resolved)
    return tuple(expanded)


def _normalize_cache_part(part: Any) -> str:
    if part is None:
        return "none"
    if isinstance(part, (datetime, date)):
        return part.isoformat()
    if isinstance(part, Decimal):
        return str(part)
    if isinstance(part, (dict, list, tuple, set)):
        payload = json.dumps(part, sort_keys=True, default=str, separators=(",", ":"))
        return _shorten(payload)
    return _shorten(str(part).replace(":", "_").replace(" ", "_"))


def _shorten(value: str) -> str:
    if len(value) <= 80:
        return value
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return f"sha1_{digest}"


def _clone_cache_value(value):
    try:
        return copy.deepcopy(value)
    except Exception:
        logger.debug("Cache value deepcopy failed; returning original value.", exc_info=True)
        return value
