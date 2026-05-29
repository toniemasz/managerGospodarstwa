from typing import Dict, Any
from decimal import Decimal
from sales.infrastructure.repositories import SaleRepository


class SaleDashboardService:
    def __init__(self, repository: SaleRepository = None):
        self.repository = repository or SaleRepository()

    def get_dashboard_summary(self) -> Dict[str, Any]:
        sales = self.repository.get_all_sales()

        total_pigs = sum(sale.quantity for sale in sales)
        total_weight = sum(sale.total_weight for sale in sales)
        total_revenue = sum(sale.total_price for sale in sales)

        avg_price_per_kg = (total_revenue / total_weight) if total_weight > 0 else Decimal('0.00')

        return {
            'sales': sales,
            'stats': {
                'total_pigs': total_pigs,
                'total_weight': total_weight,
                'total_revenue': total_revenue,
                'avg_price_per_kg': round(avg_price_per_kg, 2)
            }
        }