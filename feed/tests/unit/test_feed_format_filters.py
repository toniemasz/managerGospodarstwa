from decimal import Decimal

from feed.templatetags.feed_format import feed_money, feed_price, feed_quantity


def test_feed_quantity_uses_tonnes_for_large_values_and_strips_zero_decimals():
    assert feed_quantity(Decimal("999.50")) == "999,5 kg"
    assert feed_quantity(Decimal("2000.00")) == "2 t"
    assert feed_quantity(Decimal("2350.00")) == "2,35 t"


def test_feed_price_can_display_per_kg_or_per_tonne():
    assert feed_price(Decimal("1.20000"), "kg") == "1,2 PLN/kg"
    assert feed_price(Decimal("1.20000"), "ton") == "1 200 PLN/t"
    assert feed_price(None, "ton") == "Brak ceny"


def test_feed_money_keeps_thousand_grouping():
    assert feed_money(Decimal("2000000.00")) == "2 000 000 PLN"
