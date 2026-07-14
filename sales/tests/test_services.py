from decimal import Decimal
from datetime import date
from unittest.mock import Mock
from sales.services.sale_dashboard_service import SaleDashboardService
from sales.services.sale_entities import PigSaleEntity


def _dashboard_service(repository, *, report):
    reporting = Mock()
    reporting.summary.return_value = report
    feed_reporting = Mock()
    feed_reporting.summary.return_value = {
        "quantity_kg": Decimal("0.00"),
        "total_cost": Decimal("0.00"),
        "average_cost_per_kg": Decimal("0.00"),
        "average_cost_per_ton": Decimal("0.00"),
    }
    return SaleDashboardService(
        repository=repository,
        reporting_service=reporting,
        feed_reporting_service=feed_reporting,
    )


def _report(*, count=0, pigs=0, weight=Decimal("0.00"), net=Decimal("0.00")):
    return {
        "sale_count": count,
        "sold_quantity": pigs,
        "slaughter_weight_kg": weight,
        "live_weight_kg": Decimal("0.00"),
        "net_sales": net,
        "gross_sales": Decimal("0.00"),
        "vat_sales": Decimal("0.00"),
        "average_price_per_kg": net / weight if weight else Decimal("0.00"),
        "average_slaughter_weight_per_pig": weight / pigs if pigs else Decimal("0.00"),
        "average_meatiness": None,
    }


def test_dashboard_service_calculates_stats_correctly():
    # Arrange
    sale1 = PigSaleEntity(id=1, sale_date=date.today(), quantity=10, total_weight=Decimal('1000.00'), meat_class='E',
                          price_per_kg=Decimal('8.00'), net_value=Decimal('8000.00'), gross_value=Decimal('8640.00'))
    sale2 = PigSaleEntity(id=2, sale_date=date.today(), quantity=5, total_weight=Decimal('500.00'), meat_class='U',
                          price_per_kg=Decimal('7.00'), net_value=Decimal('3500.00'), gross_value=Decimal('3780.00'))

    mock_repo = Mock()
    mock_repo.get_all_sales.return_value = [sale1, sale2]

    service = _dashboard_service(
        mock_repo,
        report=_report(count=2, pigs=15, weight=Decimal("1500.00"), net=Decimal("11500.00")),
    )

    # Act
    result = service.get_dashboard_summary()
    stats = result['stats']

    # Assert
    assert stats['total_pigs'] == 15
    assert stats['total_weight'] == Decimal('1500.00')
    assert stats['total_net_revenue'] == Decimal('11500.00')
    assert stats['avg_price_per_kg'] == round(Decimal('11500.00') / Decimal('1500.00'), 2)


def test_dashboard_service_handles_empty_sales():
    mock_repo = Mock()
    mock_repo.get_all_sales.return_value = []

    result = _dashboard_service(mock_repo, report=_report()).get_dashboard_summary()

    assert result['sales'] == []
    assert result['stats']['total_pigs'] == 0
    assert result['stats']['total_weight'] == 0
    assert result['stats']['total_net_revenue'] == 0
    assert result['stats']['avg_price_per_kg'] == Decimal('0.00')


def test_dashboard_service_filters_sales_by_date_range():
    sale_in_range = PigSaleEntity(
        id=1,
        sale_date=date(2026, 6, 10),
        quantity=10,
        total_weight=Decimal('1000.00'),
        meat_class='E',
        price_per_kg=Decimal('8.00'),
    )
    sale_outside_range = PigSaleEntity(
        id=2,
        sale_date=date(2026, 1, 10),
        quantity=5,
        total_weight=Decimal('500.00'),
        meat_class='U',
        price_per_kg=Decimal('7.00'),
    )
    mock_repo = Mock()
    mock_repo.get_sales_between.return_value = [sale_in_range]

    result = _dashboard_service(
        mock_repo,
        report=_report(count=1, pigs=10, weight=Decimal("1000.00")),
    ).get_dashboard_summary(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )

    mock_repo.get_sales_between.assert_called_once_with(
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    assert result['sales'] == [sale_in_range]
    assert result['stats']['sale_count'] == 1
    assert result['stats']['total_pigs'] == 10
