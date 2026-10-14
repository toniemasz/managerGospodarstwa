from datetime import date

import pytest
from django.contrib.auth.models import User
from django.http import Http404

from farms.services.farm_service import get_or_create_user_farm
from sales.models import PigSaleModel
from sales.selectors import sale_for_farm, sales_for_farm


@pytest.mark.django_db
def test_sales_selectors_apply_farm_and_date_scope():
    owner = User.objects.create_user(username="selector-owner")
    farm = get_or_create_user_farm(owner)
    other = User.objects.create_user(username="selector-other")
    other_farm = get_or_create_user_farm(other)
    expected = PigSaleModel.objects.create(farm=farm, sale_date=date(2026, 6, 15))
    PigSaleModel.objects.create(farm=farm, sale_date=date(2026, 5, 31))
    foreign = PigSaleModel.objects.create(farm=other_farm, sale_date=date(2026, 6, 15))

    selected = list(sales_for_farm(
        farm,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    ))

    assert selected == [expected]
    assert sale_for_farm(farm, expected.pk) == expected
    with pytest.raises(Http404):
        sale_for_farm(farm, foreign.pk)


@pytest.mark.django_db
def test_sales_selector_query_count_is_constant(django_assert_num_queries):
    owner = User.objects.create_user(username="selector-query-owner")
    farm = get_or_create_user_farm(owner)
    PigSaleModel.objects.bulk_create([
        PigSaleModel(farm=farm, sale_date=date(2026, 6, day))
        for day in range(1, 11)
    ])

    with django_assert_num_queries(1):
        sales = list(sales_for_farm(farm))

    assert len(sales) == 10
