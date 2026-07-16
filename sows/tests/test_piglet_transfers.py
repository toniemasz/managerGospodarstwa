from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.urls import reverse

from farms.models import FarmModel
from sows.actions.events import SowEventActions
from sows.actions.mortality import create_mortality_report
from sows.actions.piglet_transfers import PigletTransferActions
from sows.forms import MortalityReportForm, PigletTransferForm, SowEventForm
from sows.models import MortalityReportModel, PigletTransferModel, SowEventModel, SowModel
from sows.services.piglet_care import PigletCareService
from sows.services.reporting import SowReportingService
from sows.services.sow_repository import SowRepository


FARROWING_DATE = date(2026, 7, 1)
TRANSFER_DATE = date(2026, 7, 5)


@pytest.fixture
def piglet_farm(django_user_model):
    owner = django_user_model.objects.create_user(username="piglet-owner", password="test")
    return FarmModel.objects.create(owner=owner, name="Test odchowu")


@pytest.fixture
def cycles(piglet_farm):
    rows = []
    for ear_tag, born_alive in (("A", 12), ("B", 8), ("C", 20)):
        sow = SowModel.objects.create(farm=piglet_farm, ear_tag=ear_tag, entry_date=date(2026, 1, 1))
        farrowing = SowEventModel.objects.create(
            sow=sow,
            event_type="FARROWING",
            event_date=FARROWING_DATE,
            details={"born_alive": born_alive, "born_dead": 0},
        )
        rows.append((sow, farrowing))
    return rows


def create_transfer(farm, cycles, quantity=3):
    return PigletTransferActions(farm).create(
        source_farrowing=cycles[0][1],
        target_farrowing=cycles[1][1],
        quantity=quantity,
        transfer_date=TRANSFER_DATE,
        note="Wyrównanie miotów",
    )


@pytest.mark.django_db
def test_transfer_changes_care_balance_but_not_biological_births(piglet_farm, cycles):
    transfer = create_transfer(piglet_farm, cycles)
    care = PigletCareService(piglet_farm)

    assert care.balance(cycles[0][1]).available == 9
    assert care.balance(cycles[1][1]).available == 11
    assert transfer.source_farrowing.details["born_alive"] == 12
    assert transfer.target_farrowing.details["born_alive"] == 8


@pytest.mark.django_db
def test_statistics_keep_biological_births_and_care_transfers_separate(piglet_farm, cycles):
    create_transfer(piglet_farm, cycles)

    summary = SowReportingService(piglet_farm).summary(
        date_from=FARROWING_DATE,
        date_to=TRANSFER_DATE,
    )

    assert summary["born_alive"] == 40
    assert summary["piglets_received"] == 3
    assert summary["piglets_transferred"] == 3
    assert summary["monthly"][0]["piglets_received"] == 3


@pytest.mark.django_db
def test_receiving_sow_can_wean_more_than_it_biologically_bore(piglet_farm, cycles):
    create_transfer(piglet_farm, cycles)
    sow_b = cycles[1][0]

    result = SowEventActions(piglet_farm).create_event(
        sow=sow_b,
        sow_status="LACTATING",
        data={"event_type": "WEANING", "event_date": date(2026, 7, 28), "count": 11},
    )

    assert result.created_event.details["count"] == 11
    assert PigletCareService(piglet_farm).balance(cycles[1][1]).available == 0


@pytest.mark.django_db
def test_pre_weaning_death_reduces_care_not_born_alive_and_limits_weaning(piglet_farm, cycles):
    create_transfer(piglet_farm, cycles)
    sow_b, farrowing_b = cycles[1]
    create_mortality_report(
        farm=piglet_farm,
        data={
            "mortality_type": MortalityReportModel.TYPE_PRE_WEANING,
            "sow": sow_b,
            "farrowing": farrowing_b,
            "mortality_date": date(2026, 7, 10),
            "quantity": 1,
        },
    )
    farrowing_b.refresh_from_db()

    assert PigletCareService(piglet_farm).balance(farrowing_b).available == 10
    assert farrowing_b.details["born_alive"] == 8
    with pytest.raises(ValidationError, match="Dostępne obecnie: 10"):
        SowEventActions(piglet_farm).create_event(
            sow=sow_b,
            sow_status="LACTATING",
            data={"event_type": "WEANING", "event_date": date(2026, 7, 28), "count": 11},
        )


@pytest.mark.django_db
def test_weaning_and_mortality_forms_use_current_care_balance(piglet_farm, cycles):
    create_transfer(piglet_farm, cycles)
    sow_b = cycles[1][0]

    valid_weaning = SowEventForm(
        farm=piglet_farm,
        sow=sow_b,
        sow_status="LACTATING",
        data={
            "event_type": "WEANING",
            "event_date": date(2026, 7, 15),
            "count": 11,
        },
    )
    excessive_weaning = SowEventForm(
        farm=piglet_farm,
        sow=sow_b,
        sow_status="LACTATING",
        data={
            "event_type": "WEANING",
            "event_date": date(2026, 7, 15),
            "count": 12,
        },
    )
    excessive_mortality = MortalityReportForm(
        farm=piglet_farm,
        data={
            "mortality_type": MortalityReportModel.TYPE_PRE_WEANING,
            "sow": sow_b.ear_tag,
            "mortality_date": date(2026, 7, 15),
            "quantity": 12,
        },
    )

    assert valid_weaning.is_valid() is True
    assert excessive_weaning.is_valid() is False
    assert "Dostępne obecnie: 11" in excessive_weaning.errors["count"][0]
    assert excessive_mortality.is_valid() is False
    assert "ujemny stan odchowu" in excessive_mortality.errors["quantity"][0]


@pytest.mark.django_db
def test_weaning_view_shows_full_current_care_summary(piglet_farm, cycles, client):
    client.force_login(piglet_farm.owner)
    create_transfer(piglet_farm, cycles)

    response = client.get(
        reverse("add_event", args=[cycles[1][0].id]),
        {"event_type": "WEANING"},
    )
    content = response.content.decode()

    assert response.status_code == 200
    for label in (
        "Urodzone żywe",
        "Przyjęte",
        "Przekazane",
        "Upadki przed odsadzeniem",
        "Już odsadzone",
        "Dostępne obecnie",
    ):
        assert label in content
    assert ">11<" in content


@pytest.mark.django_db
def test_transfer_validation_blocks_excess_same_sow_foreign_farm_and_invalid_dates(
    piglet_farm, cycles, django_user_model
):
    actions = PigletTransferActions(piglet_farm)
    common = {
        "source_farrowing": cycles[0][1],
        "target_farrowing": cycles[1][1],
        "transfer_date": TRANSFER_DATE,
    }
    with pytest.raises(ValidationError):
        actions.create(quantity=13, **common)
    with pytest.raises(ValidationError, match="muszą być różne"):
        actions.create(
            source_farrowing=cycles[0][1],
            target_farrowing=cycles[0][1],
            quantity=1,
            transfer_date=TRANSFER_DATE,
        )
    with pytest.raises(ValidationError, match="źródłowy"):
        actions.create(quantity=1, **{**common, "transfer_date": date(2026, 6, 30)})

    other_owner = django_user_model.objects.create_user(username="piglet-other")
    other_farm = FarmModel.objects.create(owner=other_owner, name="Inne")
    other_sow = SowModel.objects.create(farm=other_farm, ear_tag="OTHER")
    other_farrowing = SowEventModel.objects.create(
        sow=other_sow,
        event_type="FARROWING",
        event_date=FARROWING_DATE,
        details={"born_alive": 10},
    )
    with pytest.raises(ValidationError, match="bieżącym gospodarstwie"):
        actions.create(
            source_farrowing=cycles[0][1],
            target_farrowing=other_farrowing,
            quantity=1,
            transfer_date=TRANSFER_DATE,
        )

    SowEventModel.objects.create(
        sow=cycles[0][0], event_type="WEANING", event_date=date(2026, 7, 20), details={"count": 12}
    )
    with pytest.raises(ValidationError, match="źródłowy"):
        actions.create(quantity=1, **{**common, "transfer_date": date(2026, 7, 21)})


@pytest.mark.django_db
def test_transfer_is_one_record_visible_in_both_sow_histories(piglet_farm, cycles):
    transfer = create_transfer(piglet_farm, cycles)

    source = SowRepository(piglet_farm).get_sow_by_id(cycles[0][0].id)
    target = SowRepository(piglet_farm).get_sow_by_id(cycles[1][0].id)

    assert PigletTransferModel.objects.count() == 1
    assert any(event.transfer_id == transfer.id and event.event_type == "PIGLET_TRANSFER_OUT" for event in source.all_events)
    assert any(event.transfer_id == transfer.id and event.event_type == "PIGLET_TRANSFER_IN" for event in target.all_events)


@pytest.mark.django_db
def test_partial_weanings_are_summed_in_one_cycle(piglet_farm, cycles):
    sow_a, farrowing_a = cycles[0]
    SowEventModel.objects.create(
        sow=sow_a, event_type="WEANING", event_date=date(2026, 7, 20), details={"count": 4}
    )
    SowEventModel.objects.create(
        sow=sow_a, event_type="WEANING", event_date=date(2026, 7, 21), details={"count": 3}
    )

    balance = PigletCareService(piglet_farm).balance(farrowing_a)

    assert balance.weaned == 7
    assert balance.available == 5


@pytest.mark.django_db
def test_edit_or_cancel_transfer_cannot_make_later_history_negative(piglet_farm, cycles):
    transfer = create_transfer(piglet_farm, cycles)
    PigletTransferActions(piglet_farm).create(
        source_farrowing=cycles[1][1],
        target_farrowing=cycles[2][1],
        quantity=11,
        transfer_date=date(2026, 7, 10),
    )
    actions = PigletTransferActions(piglet_farm)

    with pytest.raises(ValidationError, match="ujemny stan"):
        actions.update(
            transfer_id=transfer.id,
            source_farrowing=cycles[0][1],
            target_farrowing=cycles[1][1],
            quantity=2,
            transfer_date=TRANSFER_DATE,
        )
    with pytest.raises(ValidationError, match="ujemny stan"):
        actions.cancel(transfer_id=transfer.id)

    transfer.refresh_from_db()
    assert transfer.quantity == 3
    assert transfer.is_canceled is False


@pytest.mark.django_db
def test_transfer_form_and_views_are_farm_scoped(piglet_farm, cycles, client, django_user_model):
    client.force_login(piglet_farm.owner)
    other_owner = django_user_model.objects.create_user(username="form-other")
    other_farm = FarmModel.objects.create(owner=other_owner, name="Inne")
    other_sow = SowModel.objects.create(farm=other_farm, ear_tag="FOREIGN")
    other_target_sow = SowModel.objects.create(farm=other_farm, ear_tag="FOREIGN-TARGET")
    other_farrowing = SowEventModel.objects.create(
        sow=other_sow,
        event_type="FARROWING",
        event_date=FARROWING_DATE,
        details={"born_alive": 10},
    )
    other_target_farrowing = SowEventModel.objects.create(
        sow=other_target_sow,
        event_type="FARROWING",
        event_date=FARROWING_DATE,
        details={"born_alive": 10},
    )
    foreign_transfer = PigletTransferModel.objects.create(
        farm=other_farm,
        source_farrowing=other_farrowing,
        target_farrowing=other_target_farrowing,
        quantity=1,
        transfer_date=TRANSFER_DATE,
    )
    form = PigletTransferForm(
        farm=piglet_farm,
        data={
            "source_farrowing": cycles[0][0].ear_tag,
            "target_farrowing": other_sow.ear_tag,
            "quantity": 1,
            "transfer_date": TRANSFER_DATE.isoformat(),
        },
    )
    assert form.is_valid() is False
    assert "target_farrowing" in form.errors

    blocked_response = client.post(reverse("add_piglet_transfer"), {
        "source_farrowing": cycles[0][0].ear_tag,
        "target_farrowing": other_sow.ear_tag,
        "quantity": 1,
        "transfer_date": TRANSFER_DATE.isoformat(),
    })
    assert blocked_response.status_code == 200
    assert not PigletTransferModel.objects.filter(
        farm=piglet_farm,
        target_farrowing=other_farrowing,
    ).exists()

    response = client.post(reverse("add_piglet_transfer"), {
        "source_farrowing": cycles[0][0].ear_tag,
        "target_farrowing": cycles[1][0].ear_tag,
        "quantity": 3,
        "transfer_date": TRANSFER_DATE.isoformat(),
        "note": "Test widoku",
    })
    assert response.status_code == 302
    list_response = client.get(reverse("piglet_transfer_list"))
    content = list_response.content.decode()
    assert "Test widoku" in content
    assert "FOREIGN" not in content
    assert client.get(reverse("edit_piglet_transfer", args=[foreign_transfer.id])).status_code == 404
    assert client.post(reverse("cancel_piglet_transfer", args=[foreign_transfer.id])).status_code == 302
    foreign_transfer.refresh_from_db()
    assert foreign_transfer.is_canceled is False


@pytest.mark.django_db
def test_transfer_form_lists_only_active_sources_with_available_piglets(piglet_farm, cycles):
    PigletTransferActions(piglet_farm).create(
        source_farrowing=cycles[0][1],
        target_farrowing=cycles[1][1],
        quantity=12,
        transfer_date=TRANSFER_DATE,
    )

    form = PigletTransferForm(farm=piglet_farm)

    source_tags = {suggestion["ear_tag"] for suggestion in form.source_suggestions}
    target_tags = {suggestion["ear_tag"] for suggestion in form.target_suggestions}

    assert cycles[0][0].ear_tag not in source_tags
    assert cycles[0][0].ear_tag in target_tags
    assert cycles[1][0].ear_tag in source_tags


@pytest.mark.django_db
def test_transfer_form_rejects_unknown_sow_number(piglet_farm, cycles):
    form = PigletTransferForm(
        farm=piglet_farm,
        data={
            "source_farrowing": "NIE-ISTNIEJE",
            "target_farrowing": cycles[1][0].ear_tag,
            "quantity": 1,
            "transfer_date": TRANSFER_DATE.isoformat(),
        },
    )

    assert form.is_valid() is False
    assert "Nie znaleziono maciory" in form.errors["source_farrowing"][0]


@pytest.mark.django_db
def test_sow_with_transfer_history_cannot_be_physically_deleted(piglet_farm, cycles, client):
    client.force_login(piglet_farm.owner)
    create_transfer(piglet_farm, cycles)

    response = client.post(
        reverse("delete_sow", args=[cycles[0][0].id]),
        follow=True,
    )

    assert response.status_code == 200
    assert SowModel.objects.filter(pk=cycles[0][0].id).exists()
    assert "Nie można usunąć maciory powiązanej z historią odchowu" in response.content.decode()


@pytest.mark.django_db
def test_active_balance_query_count_does_not_grow_with_number_of_sows(
    piglet_farm,
    cycles,
    django_assert_num_queries,
):
    for index in range(5):
        sow = SowModel.objects.create(farm=piglet_farm, ear_tag=f"EXTRA-{index}")
        SowEventModel.objects.create(
            sow=sow,
            event_type="FARROWING",
            event_date=FARROWING_DATE,
            details={"born_alive": 10},
        )

    with django_assert_num_queries(4):
        balances = PigletCareService(piglet_farm).active_balances(as_of=TRANSFER_DATE)

    assert len(balances) == 8


@pytest.mark.django_db(transaction=True)
def test_concurrent_transfers_cannot_exceed_available_stock(piglet_farm, cycles):
    barrier = Barrier(2)

    def perform(target_farrowing):
        close_old_connections()
        barrier.wait()
        try:
            PigletTransferActions(piglet_farm).create(
                source_farrowing=cycles[0][1],
                target_farrowing=target_farrowing,
                quantity=8,
                transfer_date=TRANSFER_DATE,
            )
            return "created"
        except ValidationError:
            return "blocked"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(perform, (cycles[1][1], cycles[2][1])))

    assert sorted(results) == ["blocked", "created"]
    assert PigletTransferModel.objects.filter(source_farrowing=cycles[0][1]).count() == 1
