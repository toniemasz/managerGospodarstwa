from datetime import date

import pytest
from django.urls import reverse
from django.core.exceptions import ValidationError

from farms.models import FarmModel
from sows.models import MortalityReportModel, SowEventModel, SowModel
from sows.actions.mortality import create_mortality_report, delete_mortality_report, update_mortality_report
from sows.selectors.mortality import post_weaning_stock_summary, pre_weaning_mortality_cycles


@pytest.fixture
def mortality_farm(django_user_model):
    owner = django_user_model.objects.create_user(username="mortality-domain-owner", password="test")
    return FarmModel.objects.create(owner=owner, name="Test upadków")


@pytest.fixture
def mortality_client(client, mortality_farm):
    client.force_login(mortality_farm.owner)
    client.farm = mortality_farm
    return client


@pytest.mark.django_db
def test_pre_weaning_mortality_is_calculated_per_cycle(mortality_farm):
    farm = mortality_farm
    sow = SowModel.objects.create(farm=farm, ear_tag="M-1")
    SowEventModel.objects.create(sow=sow, event_type="FARROWING", event_date=date(2026, 1, 1), details={"born_alive": 12})
    SowEventModel.objects.create(sow=sow, event_type="WEANING", event_date=date(2026, 1, 28), details={"count": 10})
    SowEventModel.objects.create(sow=sow, event_type="FARROWING", event_date=date(2026, 6, 1), details={"born_alive": 11})
    SowEventModel.objects.create(sow=sow, event_type="WEANING", event_date=date(2026, 6, 28), details={"count": 8})

    assert [row.quantity for row in pre_weaning_mortality_cycles(farm)] == [2, 3]


@pytest.mark.django_db
def test_pre_weaning_mortality_sums_partial_weanings_in_one_cycle(mortality_farm):
    sow = SowModel.objects.create(farm=mortality_farm, ear_tag="M-PARTIAL")
    SowEventModel.objects.create(
        sow=sow,
        event_type="FARROWING",
        event_date=date(2026, 1, 1),
        details={"born_alive": 12},
    )
    SowEventModel.objects.create(
        sow=sow,
        event_type="WEANING",
        event_date=date(2026, 1, 20),
        details={"count": 4},
    )
    last_weaning = SowEventModel.objects.create(
        sow=sow,
        event_type="WEANING",
        event_date=date(2026, 1, 25),
        details={"count": 3},
    )

    row = pre_weaning_mortality_cycles(mortality_farm)[0]

    assert row.quantity == 5
    assert row.weaning == last_weaning
    assert row.mortality_date == date(2026, 1, 25)


@pytest.mark.django_db
def test_missing_weaning_is_unavailable_not_zero(mortality_farm):
    farm = mortality_farm
    sow = SowModel.objects.create(farm=farm, ear_tag="M-2")
    SowEventModel.objects.create(sow=sow, event_type="FARROWING", event_date=date(2026, 1, 1), details={"born_alive": 12})

    row = pre_weaning_mortality_cycles(farm)[0]
    assert row.quantity is None
    assert row.unavailable_reason == "Brak zdarzenia odsadzenia"


@pytest.mark.django_db
def test_only_post_weaning_manual_types_reduce_stock(mortality_farm):
    farm = mortality_farm
    sow = SowModel.objects.create(farm=farm, ear_tag="M-3")
    SowEventModel.objects.create(sow=sow, event_type="FARROWING", event_date=date(2026, 1, 1), details={"born_alive": 12})
    SowEventModel.objects.create(sow=sow, event_type="WEANING", event_date=date(2026, 1, 28), details={"count": 10})
    for mortality_type in (
        MortalityReportModel.TYPE_PIGLET,
        MortalityReportModel.TYPE_WEANER,
        MortalityReportModel.TYPE_FINISHER,
        MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
    ):
        MortalityReportModel.objects.create(farm=farm, mortality_type=mortality_type, mortality_date=date(2026, 2, 1), quantity=1)
    MortalityReportModel.objects.create(farm=farm, mortality_type=MortalityReportModel.TYPE_SOW, sow=sow, mortality_date=date(2026, 2, 1), quantity=1)

    assert post_weaning_stock_summary(farm) == {"weaned_total": 10, "mortality_total": 4, "current_stock": 6}


@pytest.mark.django_db
@pytest.mark.parametrize("mortality_type", [
    MortalityReportModel.TYPE_PIGLET,
    MortalityReportModel.TYPE_WEANER,
    MortalityReportModel.TYPE_FINISHER,
])
def test_create_mortality_report_supports_every_public_post_weaning_type(mortality_farm, mortality_type):
    result = create_mortality_report(
        farm=mortality_farm,
        data={
            "mortality_type": mortality_type,
            "mortality_date": date(2026, 7, 1),
            "quantity": 2,
            "reason": "Test",
        },
    )
    assert result.report.mortality_type == mortality_type
    assert result.report.sow_id is None


@pytest.mark.django_db
def test_create_sow_mortality_satisfies_database_constraint_and_archives_sow(mortality_farm):
    sow = SowModel.objects.create(farm=mortality_farm, ear_tag="M-DEATH")
    result = create_mortality_report(
        farm=mortality_farm,
        data={"mortality_type": "sow", "sow": sow, "mortality_date": date(2026, 7, 1)},
    )
    sow.refresh_from_db()
    assert result.report.mortality_type == MortalityReportModel.TYPE_SOW
    assert result.report.sow_id == sow.id
    assert result.report.quantity == 1
    assert sow.is_archived is True


@pytest.mark.django_db
def test_legacy_ambiguous_post_weaning_type_is_rejected_before_database(mortality_farm):
    with pytest.raises(ValidationError, match="Wybierz dokładny typ"):
        create_mortality_report(
            farm=mortality_farm,
            data={"mortality_type": "post_weaning", "mortality_date": date(2026, 7, 1), "quantity": 1},
        )


@pytest.mark.django_db
def test_historical_unspecified_type_cannot_be_created_through_public_action(mortality_farm):
    with pytest.raises(ValidationError, match="Nieobsługiwany typ"):
        create_mortality_report(
            farm=mortality_farm,
            data={
                "mortality_type": MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
                "mortality_date": date(2026, 7, 1),
                "quantity": 1,
            },
        )


@pytest.mark.django_db
def test_update_and_delete_mortality_report_are_farm_scoped(mortality_farm, django_user_model):
    other_owner = django_user_model.objects.create_user(username="mortality-other-owner")
    other_farm = FarmModel.objects.create(owner=other_owner, name="Inne gospodarstwo")
    report = MortalityReportModel.objects.create(
        farm=other_farm,
        mortality_type=MortalityReportModel.TYPE_PIGLET,
        mortality_date=date(2026, 7, 1),
        quantity=1,
    )
    update_data = {
        "mortality_type": MortalityReportModel.TYPE_WEANER,
        "mortality_date": date(2026, 7, 2),
        "quantity": 2,
    }
    with pytest.raises(ValidationError):
        update_mortality_report(farm=mortality_farm, report_id=report.id, data=update_data)
    with pytest.raises(ValidationError):
        delete_mortality_report(farm=mortality_farm, report_id=report.id)
    assert MortalityReportModel.objects.filter(pk=report.id).exists()


@pytest.mark.django_db
def test_update_mortality_report_reclassifies_manual_record(mortality_farm):
    report = MortalityReportModel.objects.create(
        farm=mortality_farm,
        mortality_type=MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
        mortality_date=date(2026, 7, 1),
        quantity=1,
    )
    updated = update_mortality_report(
        farm=mortality_farm,
        report_id=report.id,
        data={
            "mortality_type": MortalityReportModel.TYPE_FINISHER,
            "mortality_date": date(2026, 7, 2),
            "quantity": 3,
            "reason": "Korekta",
            "note": "Zweryfikowano",
        },
    )
    assert updated.mortality_type == MortalityReportModel.TYPE_FINISHER
    assert updated.quantity == 3
    assert updated.reason == "Korekta"
    assert updated.note == "Zweryfikowano"


@pytest.mark.django_db
def test_delete_mortality_report_removes_manual_record(mortality_farm):
    report = MortalityReportModel.objects.create(
        farm=mortality_farm,
        mortality_type=MortalityReportModel.TYPE_WEANER,
        mortality_date=date(2026, 7, 1),
        quantity=1,
    )
    delete_mortality_report(farm=mortality_farm, report_id=report.id)
    assert not MortalityReportModel.objects.filter(pk=report.id).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("mortality_type", [
    MortalityReportModel.TYPE_PIGLET,
    MortalityReportModel.TYPE_WEANER,
    MortalityReportModel.TYPE_FINISHER,
])
def test_report_mortality_view_saves_each_public_post_weaning_type(mortality_client, mortality_farm, mortality_type):
    response = mortality_client.post(reverse("report_mortality"), {
        "mortality_type": mortality_type,
        "mortality_date": "2026-07-01",
        "quantity": "2",
        "reason": "Test widoku",
    })
    assert response.status_code == 302
    assert MortalityReportModel.objects.filter(
        farm=mortality_farm,
        mortality_type=mortality_type,
        sow__isnull=True,
        quantity=2,
    ).exists()


@pytest.mark.django_db
def test_report_mortality_view_saves_sow_without_constraint_error(mortality_client, mortality_farm):
    sow = SowModel.objects.create(farm=mortality_farm, ear_tag="VIEW-SOW")
    response = mortality_client.post(reverse("report_mortality"), {
        "mortality_type": MortalityReportModel.TYPE_SOW,
        "mortality_date": "2026-07-01",
        "sow": sow.ear_tag,
    })
    assert response.status_code == 302
    assert MortalityReportModel.objects.filter(
        farm=mortality_farm,
        mortality_type=MortalityReportModel.TYPE_SOW,
        sow=sow,
        quantity=1,
    ).exists()
