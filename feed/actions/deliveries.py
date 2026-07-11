from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit
from feed.actions.inventory import InventoryActions


def create_delivery(form, *, farm, user=None):
    delivery = form.save()
    InventoryActions(farm).sync_delivery(delivery, user=user)
    invalidate_farm_cache_on_commit(farm, groups=("inventory",))
    return delivery


def update_delivery(form, *, farm, user=None):
    with transaction.atomic():
        delivery = form.save()
        InventoryActions(farm).sync_delivery(delivery, user=user)
        InventoryActions(farm).rebuild()
        invalidate_farm_cache_on_commit(farm, groups=("inventory",))
    return delivery


def delete_delivery(delivery, *, farm):
    with transaction.atomic():
        InventoryActions(farm).remove_delivery(delivery)
        delivery.delete()
        invalidate_farm_cache_on_commit(farm, groups=("inventory",))
