from typing import Dict, Any
from decimal import Decimal
from sales.services.sale_repository import SaleRepository


class SaleDashboardService:
    def __init__(self, farm=None, repository: SaleRepository = None):
        self.repository = repository or SaleRepository(farm=farm)

    def get_dashboard_summary(self, date_from=None, date_to=None) -> Dict[str, Any]:
        if date_from is not None or date_to is not None:
            sales = self.repository.get_sales_between(date_from=date_from, date_to=date_to)
        else:
            sales = self.repository.get_all_sales()

        total_pigs = sum(sale.quantity for sale in sales)
        total_weight = sum(sale.total_weight for sale in sales)
        total_net_revenue = sum(sale.net_price for sale in sales)

        avg_price_per_kg = (total_net_revenue / total_weight) if total_weight > 0 else Decimal('0.00')
        avg_weight_per_pig = (total_weight / total_pigs) if total_pigs > 0 else Decimal('0.00')

        return {
            'sales': sales,
            'stats': {
                'sale_count': len(sales),
                'total_pigs': total_pigs,
                'total_weight': total_weight,
                'total_net_revenue': total_net_revenue,
                'avg_price_per_kg': round(avg_price_per_kg, 2),
                'avg_weight_per_pig': round(avg_weight_per_pig, 2),
            }
        }
