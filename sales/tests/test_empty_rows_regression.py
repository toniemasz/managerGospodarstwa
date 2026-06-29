from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from farms.services.farm_service import get_or_create_user_farm
from sales.forms import PigSaleForm, SaleClassRowFormSet
from sales.models import PigSaleModel, SaleClassRowModel
from sales.services.sale_form_service import SaleFormService


@pytest.mark.django_db
def test_removing_all_sale_rows_clears_stale_aggregates():
    farm = get_or_create_user_farm(User.objects.create_user(username="sale-zero"))
    sale = PigSaleModel.objects.create(farm=farm, quantity=10, total_weight=1000, price_per_kg=8, net_value=8000, gross_value=8640)
    SaleClassRowModel.objects.create(sale=sale, line_no=1, quantity=10, weight=1000, price_per_kg=8, net_value=8000, gross_value=8640)
    form = PigSaleForm({"sale_date": sale.sale_date.isoformat(), "document_number": "", "tattoo": ""}, instance=sale)
    formset = SaleClassRowFormSet({
        "rows-TOTAL_FORMS": "1", "rows-INITIAL_FORMS": "0", "rows-MIN_NUM_FORMS": "0", "rows-MAX_NUM_FORMS": "1000",
        "rows-0-line_no": "1", "rows-0-DELETE": "on",
    }, prefix="rows")
    assert form.is_valid() and formset.is_valid()
    SaleFormService(farm).save_sale(form, formset, sale)
    sale.refresh_from_db()
    assert sale.quantity == 0
    assert sale.total_weight == Decimal("0")
    assert sale.net_value == Decimal("0")
    assert sale.gross_value == Decimal("0")
