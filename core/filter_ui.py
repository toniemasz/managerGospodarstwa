from datetime import date


def filter_ui_state(params, labels: dict[str, str]) -> dict:
    chips = []
    for key, label in labels.items():
        value = params.get(key)
        if value not in (None, ""):
            chips.append(f"{label}: {value}")
    return {"filters_active": bool(chips), "filter_chips": chips}


def parse_filter_date(value: str | None) -> date | None:
    """Return a valid ISO date or ignore malformed query-string input."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
