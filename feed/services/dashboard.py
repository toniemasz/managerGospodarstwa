from feed.models import DeliveryModel, ProductionModel
from feed.selectors.inventory import inventory_dashboard


class FeedDashboardProvider:
    def __init__(self, farm):
        self.farm = farm

    def inventory(self) -> dict:
        return inventory_dashboard(self.farm)

    def queued(self):
        return ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.QUEUED,
        ).select_related("recipe").order_by("date", "time", "id")

    def stage_one_done(self):
        return ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.STAGE_1_DONE,
        ).select_related("recipe").order_by("date", "time", "id")

    def recent_deliveries(self, *, limit=5):
        return DeliveryModel.objects.filter(
            ingredient__farm=self.farm,
        ).select_related("ingredient").order_by("-date", "-id")[:limit]

    def recent_productions(self, *, limit=5):
        return ProductionModel.objects.filter(
            recipe__farm=self.farm,
        ).select_related("recipe").order_by("-created_at", "-date", "-id")[:limit]

    def in_progress_count(self) -> int:
        return self.stage_one_done().count()
