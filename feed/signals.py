from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from feed.models import DeliveryModel, InventoryMovementModel, ProductionModel
from feed.services.inventory_service import InventoryMovementService


@receiver(post_save, sender=DeliveryModel)
def sync_delivery_movement(sender, instance, **kwargs):
    InventoryMovementService(instance.ingredient.farm).sync_delivery(instance)


@receiver(pre_save, sender=DeliveryModel)
def remove_stale_delivery_movement(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous_ingredient_id = DeliveryModel.objects.filter(pk=instance.pk).values_list("ingredient_id", flat=True).first()
    if previous_ingredient_id and previous_ingredient_id != instance.ingredient_id:
        InventoryMovementModel.objects.filter(
            movement_type=InventoryMovementModel.Types.DELIVERY,
            source_model=instance._meta.label,
            source_id=str(instance.pk),
        ).delete()


@receiver(post_delete, sender=DeliveryModel)
def delete_delivery_movement(sender, instance, **kwargs):
    InventoryMovementModel.objects.filter(
        farm_id=instance.ingredient.farm_id,
        movement_type=InventoryMovementModel.Types.DELIVERY,
        source_model=instance._meta.label,
        source_id=str(instance.pk),
    ).delete()


@receiver(pre_save, sender=ProductionModel)
def remember_previous_production_status(sender, instance, **kwargs):
    instance._previous_inventory_status = None
    if not instance.pk:
        return
    instance._previous_inventory_status = ProductionModel.objects.filter(
        pk=instance.pk,
    ).values_list("status", flat=True).first()


@receiver(post_save, sender=ProductionModel)
def sync_production_movement(sender, instance, **kwargs):
    if getattr(instance, "_skip_inventory_sync", False):
        return
    service = InventoryMovementService(instance.recipe.farm)
    previous_status = getattr(instance, "_previous_inventory_status", None)
    if instance.status == ProductionModel.Statuses.COMPLETED:
        if previous_status == ProductionModel.Statuses.COMPLETED:
            service.rebuild(reconstruct_production_ids={instance.pk})
        else:
            service.book_production(instance)
    elif previous_status == ProductionModel.Statuses.COMPLETED:
        service.rebuild()
    else:
        service.release_production(instance)


@receiver(pre_delete, sender=ProductionModel)
def release_production_inventory(sender, instance, **kwargs):
    InventoryMovementService(instance.recipe.farm).release_production(instance)


@receiver(post_delete, sender=ProductionModel)
def delete_production_movements(sender, instance, **kwargs):
    InventoryMovementModel.objects.filter(
        farm_id=instance.recipe.farm_id,
        movement_type=InventoryMovementModel.Types.PRODUCTION_USAGE,
        source_model=instance._meta.label,
        source_id=str(instance.pk),
    ).delete()
    if instance.status == ProductionModel.Statuses.COMPLETED:
        InventoryMovementService(instance.recipe.farm).rebuild()
