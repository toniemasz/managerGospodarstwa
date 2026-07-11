from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit
from farms.services.audit_log_service import log_action
from feed.actions.inventory import InventoryActions


def create_delivery(form, *, farm, user=None):
    with transaction.atomic():
        delivery = form.save()
        InventoryActions(farm).sync_delivery(delivery, user=user)
        invalidate_farm_cache_on_commit(farm, groups=("inventory",))
    return delivery


def create_deliveries(formset, *, farm, user=None):
    deliveries = []
    inventory = InventoryActions(farm)

    with transaction.atomic():
        for form in formset.forms:
            if formset.can_delete and form.cleaned_data.get("DELETE", False):
                continue
            if not form.has_changed():
                continue

            delivery = form.save()
            inventory.sync_delivery(delivery, user=user)
            log_action(farm=farm, user=user, action="CREATE", obj=delivery)
            deliveries.append(delivery)

        invalidate_farm_cache_on_commit(farm, groups=("inventory",))

    return deliveries


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
