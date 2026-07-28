from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone


@dataclass
class DateRange:
    period: str
    date_from: date | None
    date_to: date | None

    @property
    def date_from_value(self) -> str:
        return self.date_from.isoformat() if self.date_from else ''

    @property
    def date_to_value(self) -> str:
        return self.date_to.isoformat() if self.date_to else ''


PERIOD_OPTIONS = [
    ('3m', '3 miesiące'),
    ('6m', '6 miesięcy'),
    ('12m', 'Rok'),
    ('all', 'Cały czas'),
    ('custom', 'Własny zakres'),
]


def parse_date_range(params, default_period: str = '6m') -> DateRange:
    today = timezone.localdate()
    period = params.get('period') or default_period
    if period not in {option[0] for option in PERIOD_OPTIONS}:
        period = default_period

    if period == 'custom':
        date_from = _parse_date(params.get('date_from'))
        date_to = _parse_date(params.get('date_to')) or today
        if date_from and date_to and date_from > date_to:
            date_from, date_to = date_to, date_from
        return DateRange(period=period, date_from=date_from, date_to=date_to)

    if period == 'all':
        return DateRange(period=period, date_from=None, date_to=None)

    days_by_period = {
        '3m': 90,
        '6m': 180,
        '12m': 365,
    }
    return DateRange(
        period=period,
        date_from=today - timedelta(days=days_by_period[period]),
        date_to=today,
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
