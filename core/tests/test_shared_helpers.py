from datetime import date

from core.date_range import parse_date_range
from core.filter_ui import filter_ui_state, parse_filter_date


def test_filter_ui_state_builds_chips_only_for_present_values():
    state = filter_ui_state(
        {"status": "gotowe", "date_from": "", "date_to": None},
        {"status": "Status", "date_from": "Od", "date_to": "Do"},
    )

    assert state == {
        "filters_active": True,
        "filter_chips": ["Status: gotowe"],
    }


def test_parse_filter_date_ignores_invalid_values():
    assert parse_filter_date("2026-07-06") == date(2026, 7, 6)
    assert parse_filter_date("06.07.2026") is None
    assert parse_filter_date(None) is None


def test_parse_date_range_swaps_reversed_custom_dates():
    date_range = parse_date_range({
        "period": "custom",
        "date_from": "2026-07-31",
        "date_to": "2026-07-01",
    })

    assert date_range.period == "custom"
    assert date_range.date_from == date(2026, 7, 1)
    assert date_range.date_to == date(2026, 7, 31)
