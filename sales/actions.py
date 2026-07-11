from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.shortcuts import get_object_or_404

from common.cache import invalidate_farm_cache_on_commit
from sales.models import PigSaleModel, SaleClassRowModel


@dataclass(frozen=True)
class DeletedSale:
    model_label: str
    object_id: int
    object_repr: str


@transaction.atomic
def save_sale(*, farm, form, row_formset, sale, user=None) -> PigSaleModel:
    if sale.farm_id and sale.farm_id != farm.id:
        raise ValueError("Sprzedaż nie należy do wskazanego gospodarstwa.")
    saved_sale = form.save(commit=False)
    saved_sale.farm = farm
    saved_sale.save()
    replace_sale_rows(saved_sale, row_formset)
    invalidate_farm_cache_on_commit(farm, groups=("sales",))
    return saved_sale


def replace_sale_rows(sale: PigSaleModel, row_formset) -> None:
    sale.rows.all().delete()
    rows = []
    for index, form in enumerate(row_formset.forms, start=1):
        if form.cleaned_data.get("DELETE") or not form.has_row_data():
            continue
        rows.append(SaleClassRowModel(
            sale=sale,
            line_no=form.cleaned_data.get("line_no") or len(rows) + 1 or index,
            meat_class=form.cleaned_data.get("meat_class") or "",
            quantity=form.cleaned_data.get("quantity"),
            weight=form.cleaned_data.get("weight"),
            avg_weight=form.cleaned_data.get("avg_weight"),
            avg_meatiness=form.cleaned_data.get("avg_meatiness"),
            price_per_kg=form.cleaned_data.get("price_per_kg"),
            net_value=form.cleaned_data.get("net_value"),
            vat_value=form.cleaned_data.get("vat_value"),
            gross_value=form.cleaned_data.get("gross_value"),
        ))
    if rows:
        SaleClassRowModel.objects.bulk_create(rows)
        sale.meat_class = rows[0].meat_class or sale.meat_class
    sale.recalculate_from_rows()
    fields = ["quantity", "total_weight", "price_per_kg", "net_value", "vat_value", "gross_value"]
    if rows:
        fields.append("meat_class")
    sale.save(update_fields=fields)


@transaction.atomic
def delete_sale(farm, sale_id: int) -> DeletedSale:
    sale = get_object_or_404(PigSaleModel, pk=sale_id, farm=farm)
    deleted_sale = DeletedSale(
        model_label=sale._meta.label,
        object_id=sale.pk,
        object_repr=str(sale),
    )
    sale.delete()
    invalidate_farm_cache_on_commit(farm, groups=("sales",))
    return deleted_sale
