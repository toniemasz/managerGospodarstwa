from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum

from feed.models import DeliveryModel, FeedServingModel, FinishedFeedBatchModel, ProductionModel
from feed.selectors.inventory import inventory_dashboard
from feed.selectors.production_costs import ProductionCostSelector


ZERO = Decimal("0.00")


class FeedReportingService:
    def __init__(self, farm):
        self.farm = farm

    def summary(self, *, date_from=None, date_to=None) -> dict:
        feed = ProductionCostSelector(self.farm).calculate(date_from=date_from, date_to=date_to)
        productions = ProductionModel.objects.filter(recipe__farm=self.farm)
        if date_from:
            productions = productions.filter(date__gte=date_from)
        if date_to:
            productions = productions.filter(date__lte=date_to)
        status_rows = {
            row["status"]: row
            for row in productions.values("status").annotate(count=Count("id"), quantity_kg=Sum("quantity_kg"))
        }
        value = lambda status, field, default: status_rows.get(status, {}).get(field) or default
        completed_count = value(ProductionModel.Statuses.COMPLETED, "count", 0)
        completed_kg = feed["quantity_kg"]
        recipe_by_quantity = sorted(feed["recipe_ranking"], key=lambda row: row["quantity_kg"], reverse=True)
        feed["production"] = {
            "total_count": productions.count(),
            "queued_count": value(ProductionModel.Statuses.QUEUED, "count", 0),
            "queued_kg": value(ProductionModel.Statuses.QUEUED, "quantity_kg", ZERO),
            "in_progress_count": value(ProductionModel.Statuses.STAGE_1_DONE, "count", 0),
            "in_progress_kg": value(ProductionModel.Statuses.STAGE_1_DONE, "quantity_kg", ZERO),
            "completed_count": completed_count,
            "completed_kg": completed_kg,
            "completed_t": completed_kg / Decimal("1000.00") if completed_kg else ZERO,
            "average_completed_batch_kg": completed_kg / completed_count if completed_count else ZERO,
            "completed_cost": feed["total_cost"],
            "recipe_by_quantity": recipe_by_quantity,
            "top_recipe_by_quantity": recipe_by_quantity[0] if recipe_by_quantity else None,
        }
        feed["finished_feed_stock_kg"] = FinishedFeedBatchModel.objects.filter(
            farm=self.farm,
        ).aggregate(total=Sum("remaining_quantity_kg"))["total"] or ZERO
        servings = FeedServingModel.objects.filter(farm=self.farm)
        if date_from:
            servings = servings.filter(date__gte=date_from)
        if date_to:
            servings = servings.filter(date__lte=date_to)
        feed["served_quantity_kg"] = servings.aggregate(total=Sum("quantity_kg"))["total"] or ZERO
        return feed


class InventoryReportingService:
    def __init__(self, farm):
        self.farm = farm

    def summary(self) -> dict:
        dashboard = inventory_dashboard(self.farm)
        inventory_rows = dashboard["inventory"]
        latest_delivery = DeliveryModel.objects.filter(
            ingredient__farm=self.farm,
        ).select_related("ingredient").order_by("-date", "-id").first()
        return {
            **dashboard,
            "ingredient_count": len(inventory_rows),
            "low_stock_count": len(dashboard["low_stock_alerts"]),
            "bin_stock_kg": sum((item.current_stock for item in inventory_rows if item.is_in_bin), ZERO),
            "bag_stock_kg": sum((item.current_stock for item in inventory_rows if not item.is_in_bin), ZERO),
            "latest_delivery": latest_delivery,
        }
