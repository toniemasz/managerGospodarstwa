from datetime import date
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from costs.forms import CostForm
from costs.models import CostCategoryModel, CostModel
from costs.services import CostService
from costs.actions import delete_manual_cost, save_manual_cost, sync_production_cost
from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.statistics import FarmStatisticsService
from feed.models import ProductionModel, RecipeModel
from sales.models import PigSaleModel


LOC_MEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "cost-history-tests",
    },
}


@pytest.fixture
def cost_context(client):
    user = get_user_model().objects.create_user(username="cost-owner", password="password")
    farm = get_or_create_user_farm(user)
    client.force_login(user)
    return client, user, farm


@pytest.mark.django_db
def test_category_create_edit_and_deactivate_are_audited(cost_context):
    client, _user, farm = cost_context
    response = client.post(reverse("add_cost_category"), {"name": "Paliwo", "description": "Ciągniki"})
    category = CostCategoryModel.objects.get(farm=farm)
    assert response.status_code == 302

    client.post(reverse("edit_cost_category", args=[category.pk]), {"name": "Paliwo i oleje", "description": "Maszyny"})
    client.post(reverse("deactivate_cost_category", args=[category.pk]))
    category.refresh_from_db()

    assert category.name == "Paliwo i oleje"
    assert category.is_active is False
    assert list(AuditLogModel.objects.filter(farm=farm).values_list("action", flat=True)) == [
        "DEACTIVATE", "UPDATE", "CREATE"
    ]


@pytest.mark.django_db
def test_cost_create_edit_delete_form_and_audit(cost_context):
    client, user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    data = {
        "date": "2026-03-10",
        "amount": "450.50",
        "category": category.pk,
        "description": "Badanie stada",
        "document_number": "FV/3",
        "supplier": "Gabinet",
        "is_paid": "on",
    }
    response = client.post(reverse("add_cost"), data)
    cost = CostModel.objects.get(farm=farm)
    assert response.status_code == 302
    assert cost.created_by == user

    data.update({"amount": "500.00", "description": "Badanie i leki"})
    client.post(reverse("edit_cost", args=[cost.pk]), data)
    cost.refresh_from_db()
    assert cost.amount == Decimal("500.00")

    client.post(reverse("delete_cost", args=[cost.pk]))
    assert not CostModel.objects.filter(pk=cost.pk).exists()
    assert set(AuditLogModel.objects.filter(farm=farm).values_list("action", flat=True)) == {"CREATE", "UPDATE", "DELETE"}

    other_user = get_user_model().objects.create_user(username="cost-other")
    other_farm = get_or_create_user_farm(other_user)
    foreign_category = CostCategoryModel.objects.create(farm=other_farm, name="Obca")
    form = CostForm(data={**data, "category": foreign_category.pk}, farm=farm)
    assert not form.is_valid()


@pytest.mark.django_db
def test_cost_list_filters_summary_and_farm_isolation(cost_context):
    client, _user, farm = cost_context
    category_a = CostCategoryModel.objects.create(farm=farm, name="Energia")
    category_b = CostCategoryModel.objects.create(farm=farm, name="Transport")
    CostModel.objects.create(farm=farm, category=category_a, date=date(2026, 1, 2), amount=100, description="Prąd", is_paid=True)
    CostModel.objects.create(farm=farm, category=category_b, date=date(2026, 2, 2), amount=300, description="Przewóz", is_paid=False)
    CostModel.objects.create(farm=farm, category=category_a, date=date(2025, 1, 2), amount=900, description="Stary koszt")
    other_user = get_user_model().objects.create_user(username="hidden-cost")
    other_farm = get_or_create_user_farm(other_user)
    other_category = CostCategoryModel.objects.create(farm=other_farm, name="Sekret")
    CostModel.objects.create(farm=other_farm, category=other_category, date=date(2026, 1, 2), amount=9999, description="UKRYTY")

    response = client.get(reverse("cost_list"), {"year": 2026, "category": category_a.pk})
    content = response.content.decode()
    assert response.status_code == 200
    listed_descriptions = [cost.description for cost in response.context["costs"]]
    assert "Prąd" in content
    assert listed_descriptions == ["Prąd"]
    assert "UKRYTY" not in content
    assert response.context["summary"]["total"] == Decimal("100")

    summary = CostService.summarize(CostModel.objects.filter(farm=farm, date__year=2026))
    assert summary["paid"] == Decimal("100")
    assert summary["unpaid"] == Decimal("300")
    assert summary["largest_category"]["category__name"] == "Transport"


@pytest.mark.django_db
def test_grouped_cost_history_sums_entries_and_keeps_category_records_separate(cost_context):
    _client, _user, farm = cost_context
    veterinary = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    transport = CostCategoryModel.objects.create(farm=farm, name="Transport")
    newest = CostModel.objects.create(
        farm=farm,
        category=veterinary,
        date=date(2026, 7, 25),
        amount=Decimal("400.00"),
        description="Kontrola stada",
    )
    oldest = CostModel.objects.create(
        farm=farm,
        category=veterinary,
        date=date(2026, 7, 10),
        amount=Decimal("300.00"),
        description="Leczenie",
    )
    CostModel.objects.create(
        farm=farm,
        category=transport,
        date=date(2026, 7, 15),
        amount=Decimal("100.00"),
        description="Przewóz",
    )
    CostModel.objects.create(
        farm=farm,
        category=None,
        date=date(2026, 7, 5),
        amount=Decimal("50.00"),
        description="Koszt historyczny bez kategorii",
    )

    overview = CostService.grouped_history(CostService(farm).get_costs(year=2026))

    assert [group["name"] for group in overview["category_groups"]] == [
        "Weterynarz",
        "Transport",
        "Bez kategorii",
    ]
    veterinary_group = overview["category_groups"][0]
    assert veterinary_group["total"] == Decimal("700.00")
    assert veterinary_group["count"] == 2
    assert veterinary_group["costs"] == [newest, oldest]
    assert overview["summary"]["total"] == Decimal("850.00")


@pytest.mark.django_db
def test_grouped_cost_history_uses_alphabetical_tiebreaker(cost_context):
    _client, _user, farm = cost_context
    beta = CostCategoryModel.objects.create(farm=farm, name="Beta")
    alpha = CostCategoryModel.objects.create(farm=farm, name="Alfa")
    CostModel.objects.create(farm=farm, category=beta, date=date(2026, 1, 1), amount=100, description="B")
    CostModel.objects.create(farm=farm, category=alpha, date=date(2026, 1, 1), amount=100, description="A")

    overview = CostService.grouped_history(CostService(farm).get_costs(year=2026))

    assert [group["name"] for group in overview["category_groups"]] == ["Alfa", "Beta"]


@pytest.mark.django_db
def test_cost_filters_apply_to_category_totals_and_history(cost_context):
    client, _user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 1, 5), amount=100,
        description="Opłacony styczeń", is_paid=True,
    )
    CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 2, 5), amount=200,
        description="Nieopłacony luty", is_paid=False,
    )
    CostModel.objects.create(
        farm=farm, category=category, date=date(2025, 2, 5), amount=900,
        description="Poprzedni rok", is_paid=True,
    )

    yearly = client.get(reverse("cost_list"), {"year": 2026})
    assert yearly.context["category_groups"][0]["total"] == Decimal("300.00")
    assert [cost.description for cost in yearly.context["category_groups"][0]["costs"]] == [
        "Nieopłacony luty",
        "Opłacony styczeń",
    ]

    ranged = client.get(
        reverse("cost_list"),
        {"year": 2026, "date_from": "2026-02-01", "date_to": "2026-02-28"},
    )
    assert ranged.context["category_groups"][0]["total"] == Decimal("200.00")
    assert [cost.description for cost in ranged.context["category_groups"][0]["costs"]] == [
        "Nieopłacony luty"
    ]

    paid = client.get(reverse("cost_list"), {"year": 2026, "payment_status": "paid"})
    assert paid.context["category_groups"][0]["total"] == Decimal("100.00")
    assert [cost.description for cost in paid.context["category_groups"][0]["costs"]] == [
        "Opłacony styczeń"
    ]


@pytest.mark.django_db
def test_edit_and_delete_recalculate_grouped_cost_totals(cost_context):
    client, _user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    first = CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 7, 10), amount=300,
        description="Pierwszy koszt",
    )
    CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 7, 25), amount=400,
        description="Drugi koszt",
    )
    edit_data = {
        "date": "2026-07-10",
        "amount": "350.00",
        "category": category.pk,
        "description": "Pierwszy koszt",
        "document_number": "",
        "supplier": "",
    }

    assert client.post(reverse("edit_cost", args=[first.pk]), edit_data).status_code == 302
    edited = client.get(reverse("cost_list"), {"year": 2026})
    assert edited.context["category_groups"][0]["total"] == Decimal("750.00")
    assert edited.context["category_groups"][0]["count"] == 2

    assert client.post(reverse("delete_cost", args=[first.pk])).status_code == 302
    deleted = client.get(reverse("cost_list"), {"year": 2026})
    assert deleted.context["category_groups"][0]["total"] == Decimal("400.00")
    assert deleted.context["category_groups"][0]["count"] == 1


@pytest.mark.django_db
def test_manual_cost_delete_requires_post_and_foreign_costs_are_hidden(cost_context):
    client, _user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Energia")
    cost = CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 1, 1), amount=100,
        description="Koszt lokalny",
    )
    assert client.get(reverse("delete_cost", args=[cost.pk])).status_code == 405
    assert CostModel.objects.filter(pk=cost.pk).exists()

    other_user = get_user_model().objects.create_user(username="foreign-cost-owner")
    other_farm = get_or_create_user_farm(other_user)
    foreign_category = CostCategoryModel.objects.create(farm=other_farm, name="Obca")
    foreign_cost = CostModel.objects.create(
        farm=other_farm, category=foreign_category, date=date(2026, 1, 1), amount=999,
        description="Tajny koszt",
    )
    assert client.get(reverse("edit_cost", args=[foreign_cost.pk])).status_code == 404
    assert client.post(reverse("delete_cost", args=[foreign_cost.pk])).status_code == 404
    assert CostModel.objects.filter(pk=foreign_cost.pk).exists()


@pytest.mark.django_db
def test_automatic_feed_cost_cannot_be_edited_or_deleted_manually(cost_context):
    client, _user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Pasza chroniona")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 4, 1),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )
    cost = CostModel.objects.create(
        farm=farm,
        production=production,
        date=date(2026, 4, 1),
        amount=Decimal("123.45"),
        description="Automatyczny koszt",
        is_paid=True,
    )

    assert client.get(reverse("edit_cost", args=[cost.pk])).status_code == 302
    assert client.post(reverse("delete_cost", args=[cost.pk])).status_code == 302
    assert CostModel.objects.filter(pk=cost.pk).exists()

    content = client.get(reverse("cost_list"), {"year": 2026}).content.decode()
    assert "Automatyczny koszt paszy" in content
    assert "Zobacz śrutowanie" in content
    assert 'data-no-pagination="true"' in content
    assert f'action="{reverse("delete_cost", args=[cost.pk])}"' not in content


@pytest.mark.django_db
def test_grouped_history_fetches_related_history_without_n_plus_one(cost_context, django_assert_num_queries):
    _client, user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 1, 1), amount=100,
        description="Kontrola", created_by=user,
    )

    with django_assert_num_queries(1):
        overview = CostService.grouped_history(CostService(farm).get_costs(year=2026))
        history_cost = overview["category_groups"][0]["costs"][0]
        assert history_cost.category.name == "Weterynarz"
        assert history_cost.created_by.username == "cost-owner"


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db(transaction=True)
def test_manual_cost_edit_and_delete_invalidate_cached_statistics(cost_context):
    _client, user, farm = cost_context
    cache.clear()
    category = CostCategoryModel.objects.create(farm=farm, name="Weterynarz")
    cost = CostModel.objects.create(
        farm=farm, category=category, date=date(2026, 7, 10), amount=300,
        description="Badanie",
    )
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 7, 20),
        quantity=1,
        live_weight=Decimal("100.00"),
        net_value=Decimal("1000.00"),
        gross_value=Decimal("1000.00"),
    )
    period = {"date_from": date(2026, 1, 1), "date_to": date(2026, 12, 31)}
    assert FarmStatisticsService(farm).calculate(**period)["profitability"]["total_cost_per_live_kg"] == Decimal("3")

    form = CostForm(
        data={
            "date": "2026-07-10",
            "amount": "350.00",
            "category": category.pk,
            "description": "Badanie",
            "document_number": "",
            "supplier": "",
        },
        instance=cost,
        farm=farm,
    )
    assert form.is_valid()
    save_manual_cost(farm=farm, form=form, user=user)
    assert FarmStatisticsService(farm).calculate(**period)["profitability"]["total_cost_per_live_kg"] == Decimal("3.5")

    delete_manual_cost(farm=farm, cost_id=cost.pk)
    assert FarmStatisticsService(farm).calculate(**period)["profitability"]["total_cost_per_live_kg"] == Decimal("0")


@override_settings(CACHES=LOC_MEM_CACHE)
@pytest.mark.django_db(transaction=True)
def test_production_cost_sync_invalidates_cached_statistics(cost_context):
    _client, user, farm = cost_context
    cache.clear()
    recipe = RecipeModel.objects.create(farm=farm, name="Pasza cache")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 7, 10),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.COMPLETED,
        feed_cost_total=Decimal("100.00"),
    )
    sync_production_cost(farm=farm, production=production, user=user)
    PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2026, 7, 20),
        quantity=1,
        live_weight=Decimal("100.00"),
        net_value=Decimal("1000.00"),
        gross_value=Decimal("1000.00"),
    )
    period = {"date_from": date(2026, 1, 1), "date_to": date(2026, 12, 31)}
    assert FarmStatisticsService(farm).calculate(**period)["profitability"]["total_cost_per_live_kg"] == Decimal("1")

    production.feed_cost_total = Decimal("250.00")
    production.save(update_fields=("feed_cost_total",))
    sync_production_cost(farm=farm, production=production, user=user)

    assert FarmStatisticsService(farm).calculate(**period)["profitability"]["total_cost_per_live_kg"] == Decimal("2.5")


@pytest.mark.django_db
def test_empty_cost_list_has_clear_empty_state(cost_context):
    client, _user, _farm = cost_context
    response = client.get(reverse("cost_list"), {"year": 2026})
    assert "Brak kosztów" in response.content.decode()


@pytest.mark.django_db
def test_manual_cost_cannot_have_zero_amount(cost_context):
    _client, _user, farm = cost_context
    category = CostCategoryModel.objects.create(farm=farm, name="Energia")
    form = CostForm(data={
        "date": "2026-03-10",
        "amount": "0.00",
        "category": category.pk,
        "description": "Nieprawidłowy koszt",
        "document_number": "",
        "supplier": "",
    }, farm=farm)

    assert not form.is_valid()
    assert "większa od zera" in form.errors["amount"][0]


@pytest.mark.django_db(transaction=True)
def test_historical_backfill_creates_cost_even_when_fifo_amount_is_zero(cost_context):
    _client, _user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Historyczna pasza bez ceny")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2025, 1, 1),
        quantity_kg=Decimal("1000.00"),
        status=ProductionModel.Statuses.QUEUED,
        feed_cost_total=Decimal("0.00"),
        feed_cost_is_partial=True,
    )
    ProductionModel.objects.filter(pk=production.pk).update(status=ProductionModel.Statuses.COMPLETED)

    migration = import_module("costs.migrations.0002_production_costs")
    migration.backfill_production_costs(django_apps, None)
    migration.backfill_production_costs(django_apps, None)
    format_migration = import_module("costs.migrations.0003_format_feed_cost_mass_units")
    format_migration.format_feed_cost_descriptions(django_apps, None)

    cost = CostModel.objects.get(production=production)
    assert cost.amount == Decimal("0.00")
    assert cost.category.name == "Pasza"
    assert "1 t" in cost.description
    assert CostModel.objects.filter(production=production).count() == 1


@pytest.mark.django_db
def test_production_cost_sync_is_idempotent_and_farm_scoped(cost_context):
    _client, user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Koszt jawny")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 4, 1),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.QUEUED,
    )
    ProductionModel.objects.filter(pk=production.pk).update(
        status=ProductionModel.Statuses.COMPLETED,
        feed_cost_total=Decimal("123.45"),
    )
    production.refresh_from_db()

    first = sync_production_cost(farm=farm, production=production, user=user)
    ProductionModel.objects.filter(pk=production.pk).update(feed_cost_total=Decimal("150.00"))
    production.refresh_from_db()
    second = sync_production_cost(farm=farm, production=production, user=user)

    assert first.pk == second.pk
    assert CostModel.objects.filter(production=production).count() == 1
    assert CostModel.objects.get(production=production).amount == Decimal("150.00")

    other_user = get_user_model().objects.create_user(username="foreign-cost-sync")
    other_farm = get_or_create_user_farm(other_user)
    with pytest.raises(ValidationError, match="innego gospodarstwa"):
        sync_production_cost(farm=other_farm, production=production, user=other_user)


@pytest.mark.django_db
def test_cost_list_separates_source_payment_and_links_production(cost_context):
    client, _user, farm = cost_context
    recipe = RecipeModel.objects.create(farm=farm, name="Pasza testowa")
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date.today(),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.COMPLETED,
    )
    CostModel.objects.create(
        farm=farm,
        production=production,
        date=date.today(),
        amount=Decimal("123.45"),
        description="Koszt paszy",
        is_paid=True,
    )

    response = client.get(reverse("cost_list"), {"year": date.today().year})
    content = response.content.decode()

    assert response.status_code == 200
    assert ">Źródło<" in content
    assert ">Płatność<" in content
    assert "Automatyczny koszt paszy" in content
    assert "Nie dotyczy" in content
    assert "Automatyczny FIFO" not in content
    assert f'href="{reverse("production_detail", args=[production.pk])}"' in content
    assert "Zobacz śrutowanie" in content
