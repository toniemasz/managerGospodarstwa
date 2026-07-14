from farms.calculators.statistics import FeedEfficiencyCalculator
from feed.services.reporting import FeedReportingService
from sales.services.reporting import SalesReportingService
from sales.services.sale_repository import SaleRepository


class SaleDashboardService:
    """Przygotowuje listę sprzedaży, korzystając ze wspólnego raportu domenowego."""

    def __init__(self, farm=None, repository=None, reporting_service=None, feed_reporting_service=None):
        if farm is None and (repository is None or reporting_service is None):
            raise ValueError("Dashboard sprzedaży wymaga gospodarstwa albo jawnych zależności testowych.")
        self.farm = farm
        self.repository = repository or SaleRepository(farm=farm)
        self.reporting = reporting_service or SalesReportingService(farm)
        self.feed_reporting = feed_reporting_service or FeedReportingService(farm)

    def get_dashboard_summary(self, date_from=None, date_to=None) -> dict:
        if date_from is not None or date_to is not None:
            sales = self.repository.get_sales_between(date_from=date_from, date_to=date_to)
        else:
            sales = self.repository.get_all_sales()

        report = self.reporting.summary(date_from=date_from, date_to=date_to)
        feed = self.feed_reporting.summary(date_from=date_from, date_to=date_to)
        efficiency = FeedEfficiencyCalculator.calculate(sales=report, feed=feed)
        return {
            "sales": sales,
            "stats": {
                "sale_count": report["sale_count"],
                "total_pigs": report["sold_quantity"],
                "total_weight": report["slaughter_weight_kg"],
                "total_live_weight": report["live_weight_kg"],
                "total_net_revenue": report["net_sales"],
                "total_vat": report["vat_sales"],
                "total_gross_revenue": report["gross_sales"],
                "avg_price_per_kg": report["average_price_per_kg"],
                "avg_weight_per_pig": report["average_slaughter_weight_per_pig"],
                "avg_meatiness": report["average_meatiness"],
                "completed_feed_kg": feed["quantity_kg"],
                "feed_to_live_weight_ratio": efficiency["feed_to_live_weight_ratio"],
            },
        }
