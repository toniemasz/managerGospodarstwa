from django.db import transaction

from common.cache import invalidate_farm_cache_on_commit
from farms.services.audit_log_service import log_action
from feed.actions.inventory import InventoryActions
from feed.models import DeliveryModel


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
    inventory_fields = {"date", "ingredient", "quantity_kg"}
    with transaction.atomic():
        previous = (
            DeliveryModel.objects.select_for_update()
            .only("date", "ingredient_id", "quantity_kg", "price_per_kg")
            .get(pk=form.instance.pk, ingredient__farm=farm)
        )
        delivery = form.save()
        changed_fields = {
            field_name
            for field_name, old_value, new_value in (
                ("date", previous.date, delivery.date),
                ("ingredient", previous.ingredient_id, delivery.ingredient_id),
                ("quantity_kg", previous.quantity_kg, delivery.quantity_kg),
                ("price_per_kg", previous.price_per_kg, delivery.price_per_kg),
            )
            if old_value != new_value
        }
        inventory = InventoryActions(farm)
        if changed_fields & inventory_fields:
            inventory.rebuild()
        elif "price_per_kg" in changed_fields:
            inventory.sync_delivery(delivery, user=user)
        if changed_fields & (inventory_fields | {"price_per_kg"}):
            invalidate_farm_cache_on_commit(farm, groups=("inventory",))
    return delivery


def delete_delivery(delivery, *, farm):
    with transaction.atomic():
        InventoryActions(farm).remove_delivery(delivery)
        delivery.delete()
        invalidate_farm_cache_on_commit(farm, groups=("inventory",))
