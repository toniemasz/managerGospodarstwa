from decimal import Decimal
from datetime import date
from unittest.mock import Mock
from sales.domain.entities import PigSaleEntity
from sales.application.services import SaleDashboardService


def test_dashboard_service_calculates_stats_correctly():
    # Arrange
    sale1 = PigSaleEntity(id=1, sale_date=date.today(), quantity=10, total_weight=Decimal('1000.00'), meat_class='E',
                          price_per_kg=Decimal('8.00'))
    sale2 = PigSaleEntity(id=2, sale_date=date.today(), quantity=5, total_weight=Decimal('500.00'), meat_class='U',
                          price_per_kg=Decimal('7.00'))

    mock_repo = Mock()
    mock_repo.get_all_sales.return_value = [sale1, sale2]

    service = SaleDashboardService(repository=mock_repo)

    # Act
    result = service.get_dashboard_summary()
    stats = result['stats']

    # Assert
    assert stats['total_pigs'] == 15
    assert stats['total_weight'] == Decimal('1500.00')
    assert stats['total_revenue'] == Decimal('11500.00')  # (1000*8) + (500*7)
    assert stats['avg_price_per_kg'] == round(Decimal('11500.00') / Decimal('1500.00'), 2)