from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from common.cache import invalidate_farm_cache_on_commit
from sows.models import PigletTransferModel
from sows.services.piglet_care import PigletCareError, PigletCareService


class PigletTransferActions:
    """Atomowe operacje zapisu transferów prosiąt."""

    def __init__(self, farm, user=None):
        if farm is None:
            raise ValueError("Operacje transferów wymagają jawnego gospodarstwa.")
        self.farm = farm
        self.user = user
        self.care = PigletCareService(farm)

    @transaction.atomic
    def create(self, *, source_farrowing, target_farrowing, quantity, transfer_date, note=""):
        locked = self.care.lock_farrowings((source_farrowing.id, target_farrowing.id))
        source = locked[source_farrowing.id]
        target = locked[target_farrowing.id]
        self.care.validate_transfer(
            source_farrowing=source,
            target_farrowing=target,
            quantity=quantity,
            transfer_date=transfer_date,
        )
        transfer = PigletTransferModel.objects.create(
            farm=self.farm,
            source_farrowing=source,
            target_farrowing=target,
            quantity=quantity,
            transfer_date=transfer_date,
            note=note or "",
            created_by=self._authenticated_user(),
        )
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return transfer

    @transaction.atomic
    def update(
        self,
        *,
        transfer_id: int,
        source_farrowing,
        target_farrowing,
        quantity,
        transfer_date,
        note="",
    ):
        transfer = self._get_transfer(transfer_id, lock_for_update=True)
        if transfer.is_canceled:
            raise PigletCareError("Anulowanego transferu nie można edytować.")
        locked = self.care.lock_farrowings((
            transfer.source_farrowing_id,
            transfer.target_farrowing_id,
            source_farrowing.id,
            target_farrowing.id,
        ))
        transfer.source_farrowing = locked[transfer.source_farrowing_id]
        transfer.target_farrowing = locked[transfer.target_farrowing_id]
        source = locked[source_farrowing.id]
        target = locked[target_farrowing.id]
        self.care.validate_transfer(
            source_farrowing=source,
            target_farrowing=target,
            quantity=quantity,
            transfer_date=transfer_date,
            replaced_transfer=transfer,
        )
        transfer.source_farrowing = source
        transfer.target_farrowing = target
        transfer.quantity = quantity
        transfer.transfer_date = transfer_date
        transfer.note = note or ""
        transfer.save(update_fields=(
            "source_farrowing",
            "target_farrowing",
            "quantity",
            "transfer_date",
            "note",
            "updated_at",
        ))
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return transfer

    @transaction.atomic
    def cancel(self, *, transfer_id: int, reason=""):
        transfer = self._get_transfer(transfer_id, lock_for_update=True)
        if transfer.is_canceled:
            raise PigletCareError("Transfer został już anulowany.")
        locked = self.care.lock_farrowings((
            transfer.source_farrowing_id,
            transfer.target_farrowing_id,
        ))
        transfer.source_farrowing = locked[transfer.source_farrowing_id]
        transfer.target_farrowing = locked[transfer.target_farrowing_id]
        self.care.validate_transfer_cancellation(transfer)
        transfer.canceled_at = timezone.now()
        transfer.canceled_by = self._authenticated_user()
        transfer.cancellation_note = (reason or "").strip()
        transfer.save(update_fields=(
            "canceled_at",
            "canceled_by",
            "cancellation_note",
            "updated_at",
        ))
        invalidate_farm_cache_on_commit(self.farm, groups=("sows",))
        return transfer

    def _get_transfer(self, transfer_id: int, *, lock_for_update=False):
        queryset = PigletTransferModel.objects.filter(farm=self.farm).select_related(
            "source_farrowing__sow",
            "target_farrowing__sow",
        )
        if lock_for_update:
            queryset = queryset.select_for_update(of=("self",))
        transfer = queryset.filter(pk=transfer_id).first()
        if transfer is None:
            raise ValidationError("Nie znaleziono transferu w bieżącym gospodarstwie.")
        return transfer

    def _authenticated_user(self):
        return self.user if getattr(self.user, "is_authenticated", False) else None
