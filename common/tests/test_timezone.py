from datetime import date, datetime, time, timezone as datetime_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.template import Context, Template
from django.utils import timezone

from feed.selectors.productions import default_production_initial


WARSAW = ZoneInfo("Europe/Warsaw")


def test_application_uses_polish_named_timezone_with_aware_datetimes():
    assert settings.LANGUAGE_CODE == "pl"
    assert settings.TIME_ZONE == "Europe/Warsaw"
    assert settings.USE_TZ is True


def test_warsaw_timezone_applies_winter_and_summer_offsets():
    winter_utc = datetime(2026, 1, 15, 12, tzinfo=datetime_timezone.utc)
    summer_utc = datetime(2026, 7, 15, 12, tzinfo=datetime_timezone.utc)

    assert timezone.localtime(winter_utc, WARSAW).hour == 13
    assert timezone.localtime(summer_utc, WARSAW).hour == 14


def test_template_displays_aware_utc_timestamp_in_polish_local_time():
    template = Template(
        '{% load tz %}{{ winter|date:"d.m.Y H:i" }}|'
        '{{ summer|date:"d.m.Y H:i" }}'
    )
    rendered = template.render(
        Context(
            {
                "winter": datetime(
                    2026,
                    1,
                    15,
                    12,
                    tzinfo=datetime_timezone.utc,
                ),
                "summer": datetime(
                    2026,
                    7,
                    15,
                    12,
                    tzinfo=datetime_timezone.utc,
                ),
            }
        )
    )

    assert rendered == "15.01.2026 13:00|15.07.2026 14:00"


def test_date_and_local_time_values_are_not_shifted_like_instants():
    template = Template(
        '{{ calendar_day|date:"d.m.Y" }}|{{ local_hour|time:"H:i" }}'
    )

    rendered = template.render(
        Context(
            {
                "calendar_day": date(2026, 3, 29),
                "local_hour": time(14, 0),
            }
        )
    )

    assert rendered == "29.03.2026|14:00"


def test_production_form_initial_converts_utc_before_extracting_date_and_time():
    utc_instant = datetime(
        2026,
        7,
        27,
        23,
        30,
        tzinfo=datetime_timezone.utc,
    )

    initial = default_production_initial(
        None,
        current_datetime=utc_instant,
    )

    assert initial["date"] == date(2026, 7, 28)
    assert initial["time"] == "01:30"
