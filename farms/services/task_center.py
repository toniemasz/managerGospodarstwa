from __future__ import annotations

from feed.models import ProductionModel
from feed.services.feed_management_service import FeedManagementService
from sales.models import PigSaleModel
from sows.services.sow_dashboard_service import SowDashboardService


class TaskCenterService:
    def __init__(self, farm):
        self.farm = farm

    def get_tasks(self) -> dict:
        sow_tasks = SowDashboardService(farm=self.farm).get_dashboard_summary()
        feed_service = FeedManagementService(farm=self.farm)
        inventory = feed_service.get_inventory_dashboard()
        queued = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.QUEUED,
        ).select_related("recipe").order_by("date", "time", "id")
        stage_one = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.STAGE_1_DONE,
        ).select_related("recipe").order_by("date", "time", "id")
        unsettled_sales = PigSaleModel.objects.filter(
            farm=self.farm,
            no_settlement=True,
        ).order_by("sale_date", "id")
        return {
            "sows_to_check": sow_tasks["sows_to_check_usg"],
            "farrowings": sow_tasks["farrowing_due_sows"],
            "vaccination_groups": sow_tasks["vaccination_groups"],
            "low_stock": inventory["low_stock_alerts"],
            "queued_productions": queued,
            "stage_one_productions": stage_one,
            "unsettled_sales": unsettled_sales,
            "task_count": (
                len(sow_tasks["sows_to_check_usg"])
                + len(sow_tasks["farrowing_due_sows"])
                + sow_tasks["vaccinations_due_count"]
                + len(inventory["low_stock_alerts"])
                + queued.count()
                + stage_one.count()
                + unsettled_sales.count()
            ),
        }
