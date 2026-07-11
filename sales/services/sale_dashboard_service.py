from typing import Dict, Any
from decimal import Decimal
from sales.services.sale_repository import SaleRepository
from feed.services.reporting import FeedReportingService


class SaleDashboardService:
    def __init__(self, farm=None, repository: SaleRepository = None):
        if farm is None and repository is None:
            raise ValueError("Dashboard sprzedaży wymaga jawnego gospodarstwa.")
        self.farm = farm
        self.repository = repository or SaleRepository(farm=farm)

    def get_dashboard_summary(self, date_from=None, date_to=None) -> Dict[str, Any]:
        if date_from is not None or date_to is not None:
            sales = self.repository.get_sales_between(date_from=date_from, date_to=date_to)
        else:
            sales = self.repository.get_all_sales()

        total_pigs = sum(sale.quantity for sale in sales)
        total_weight = sum(sale.total_weight for sale in sales)
        total_live_weight = sum((sale.live_weight or Decimal('0.00')) for sale in sales)
        total_net_revenue = sum(sale.net_price for sale in sales)
        total_vat = sum(sale.vat_value for sale in sales)
        total_gross_revenue = sum(sale.gross_value for sale in sales)
        meatiness_values = [sale.avg_meatiness_seurop for sale in sales if sale.avg_meatiness_seurop is not None]

        avg_price_per_kg = (total_net_revenue / total_weight) if total_weight > 0 else Decimal('0.00')
        avg_weight_per_pig = (total_weight / total_pigs) if total_pigs > 0 else Decimal('0.00')
        avg_meatiness = sum(meatiness_values) / len(meatiness_values) if meatiness_values else None

        feed_kg = Decimal('0.00')
        if self.farm is not None:
            feed_kg = FeedReportingService(self.farm).summary(
                date_from=date_from,
                date_to=date_to,
            )['quantity_kg']

        return {
            'sales': sales,
            'stats': {
                'sale_count': len(sales),
                'total_pigs': total_pigs,
                'total_weight': total_weight,
                'total_live_weight': total_live_weight,
                'total_net_revenue': total_net_revenue,
                'total_vat': total_vat,
                'total_gross_revenue': total_gross_revenue,
                'avg_price_per_kg': round(avg_price_per_kg, 2),
                'avg_weight_per_pig': round(avg_weight_per_pig, 2),
                'avg_meatiness': round(avg_meatiness, 2) if avg_meatiness is not None else None,
                'completed_feed_kg': feed_kg,
                'feed_to_live_weight_ratio': feed_kg / total_live_weight if total_live_weight else None,
            }
        }
