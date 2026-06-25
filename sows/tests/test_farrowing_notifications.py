from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model

from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from sows.models import SowEventModel, SowModel
from sows.services.sow_dashboard_service import SowDashboardService


def _farm_with_sow(expected_delta):
    user = get_user_model().objects.create_user(username=f"farrowing-{expected_delta}")
    farm = get_or_create_user_farm(user)
    settings = get_farm_settings(farm)
    settings.gestation_days = 115
    settings.farrowing_alert_days_ahead = 5
    settings.save(update_fields=["gestation_days", "farrowing_alert_days_ahead"])
    today = date(2026, 6, 21)
    sow = SowModel.objects.create(farm=farm, ear_tag=f"F-{expected_delta}", entry_date=today - timedelta(days=300))
    insemination = today + timedelta(days=expected_delta - settings.gestation_days)
    SowEventModel.objects.create(sow=sow, event_type="INSEMINATION", event_date=insemination)
    SowEventModel.objects.create(
        sow=sow,
        event_type="PREGNANCY_CHECK",
        event_date=insemination + timedelta(days=30),
        details={"result": "TAK"},
    )
    return farm, sow, today


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("delta", "expected_status", "expected_label"),
    [(6, None, None), (5, "upcoming", "za 5 dni"), (0, "today", "dzisiaj"), (-2, "overdue", "2 dni po terminie")],
)
def test_farrowing_notification_window_and_status(delta, expected_status, expected_label):
    farm, _sow, today = _farm_with_sow(delta)
    notifications = SowDashboardService(farm=farm).get_notifications(current_date=today)
    items = notifications["farrowing_due_sows"]
    if expected_status is None:
        assert items == []
    else:
        assert len(items) == 1
        assert items[0]["alert_status"] == expected_status
        assert items[0]["time_label"] == expected_label


@pytest.mark.django_db
def test_farrowing_notification_disappears_after_farrowing_event():
    farm, sow, today = _farm_with_sow(-1)
    SowEventModel.objects.create(
        sow=sow,
        event_type="FARROWING",
        event_date=today,
        details={"born_alive": 12, "born_dead": 0},
    )
    notifications = SowDashboardService(farm=farm).get_notifications(current_date=today)
    assert notifications["farrowing_due_sows"] == []
