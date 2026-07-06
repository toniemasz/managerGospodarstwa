from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.shortcuts import get_object_or_404

from sales.models import PigSaleModel


@dataclass(frozen=True)
class DeletedSale:
    model_label: str
    object_id: int
    object_repr: str


@transaction.atomic
def delete_sale(farm, sale_id: int) -> DeletedSale:
    sale = get_object_or_404(PigSaleModel, pk=sale_id, farm=farm)
    deleted_sale = DeletedSale(
        model_label=sale._meta.label,
        object_id=sale.pk,
        object_repr=str(sale),
    )
    sale.delete()
    return deleted_sale
