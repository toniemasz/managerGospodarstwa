import pytest
from decimal import Decimal
from datetime import date
from feed.forms import DeliveryForm
from feed.models import IngredientModel

@pytest.mark.django_db
def test_delivery_form_valid_data():
    ing = IngredientModel.objects.create(name="Pszenżyto")
    form_data = {
        'date': date.today(),
        'ingredient': ing.id,
        'quantity_kg': Decimal('500.50'),
        'price_per_kg': Decimal('0.90')
    }
    form = DeliveryForm(data=form_data)
    assert form.is_valid() is True

@pytest.mark.django_db
def test_delivery_form_invalid_missing_ingredient():
    form_data = {
        'date': date.today(),
        'quantity_kg': Decimal('500.50'),
    }
    form = DeliveryForm(data=form_data)
    assert form.is_valid() is False
    assert 'ingredient' in form.errors