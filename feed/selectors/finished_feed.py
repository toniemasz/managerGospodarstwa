from decimal import Decimal

from django.db.models import Sum

from feed.models import FeedProductModel, FeedServingModel, FinishedFeedBatchModel, ReadyFeedDeliveryModel


def finished_feed_inventory_context(farm):
    products = list(
        FeedProductModel.objects.filter(farm=farm)
        .annotate(stock_kg=Sum("batches__remaining_quantity_kg"))
        .select_related("recipe")
        .order_by("name")
    )
    return {
        "products": products,
        "total_finished_feed_kg": sum((item.stock_kg or Decimal("0.00") for item in products), Decimal("0.00")),
        "batches": FinishedFeedBatchModel.objects.filter(farm=farm).select_related("product", "production", "ready_feed_delivery").order_by("batch_date", "id"),
        "deliveries": ReadyFeedDeliveryModel.objects.filter(farm=farm).select_related("product").order_by("-date", "-id"),
    }


def feed_servings_context(farm):
    return {
        "servings": FeedServingModel.objects.filter(farm=farm).select_related("product", "automatic_for_production").prefetch_related("allocations__batch").order_by("-date", "-time", "-id"),
    }
