from decimal import Decimal
from unittest.mock import Mock
from feed.domain.entities import InventoryItem
from feed.application.services import FeedManagementService


def test_feed_service_generates_low_stock_alerts():
    # Arrange
    item_ok = InventoryItem(1, "Soja", Decimal('2000.00'), Decimal('1000.00'))  # Zostaje 1000 (>500)
    item_low = InventoryItem(2, "Premiks", Decimal('1000.00'), Decimal('800.00'))  # Zostaje 200 (<500)

    mock_repo = Mock()
    mock_repo.get_inventory_state.return_value = [item_ok, item_low]

    service = FeedManagementService(repository=mock_repo)

    # Act
    dashboard_data = service.get_inventory_dashboard()

    # Assert
    assert len(dashboard_data['inventory']) == 2
    assert len(dashboard_data['low_stock_alerts']) == 1
    assert dashboard_data['low_stock_alerts'][0].ingredient_name == "Premiks"
    mock_repo.get_inventory_state.assert_called_once()