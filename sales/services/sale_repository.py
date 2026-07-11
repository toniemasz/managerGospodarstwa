from typing import List
from django.shortcuts import get_object_or_404
from sales.models import PigSaleModel
from sales.services.sale_entities import PigSaleEntity


class SaleRepository:
    def __init__(self, farm):
        if farm is None:
            raise ValueError("Repozytorium sprzedaży wymaga jawnego gospodarstwa.")
        self.farm = farm

    def _filter_for_farm(self, **extra_filters):
        extra_filters['farm'] = self.farm
        return extra_filters

    def _map_to_entity(self, db_model: PigSaleModel) -> PigSaleEntity:
        return PigSaleEntity(
            id=db_model.id,
            sale_date=db_model.sale_date,
            quantity=db_model.quantity,
            total_weight=db_model.total_weight,
            meat_class=db_model.meat_class,
            price_per_kg=db_model.price_per_kg,
            document_number=db_model.document_number,
            no_settlement=db_model.no_settlement,
            settlement_status=db_model.settlement_status,
            avg_meatiness_seurop=db_model.avg_meatiness_seurop,
            live_weight=db_model.live_weight,
            dressing_percentage=db_model.dressing_percentage,
            net_value=db_model.net_value,
            vat_value=db_model.vat_value,
            gross_value=db_model.gross_value,
        )

    def get_all_sales(self) -> List[PigSaleEntity]:
        db_sales = PigSaleModel.objects.prefetch_related('rows').filter(**self._filter_for_farm())
        return [self._map_to_entity(sale) for sale in db_sales]

    def get_sales_between(self, date_from=None, date_to=None) -> List[PigSaleEntity]:
        filters = self._filter_for_farm()
        if date_from is not None:
            filters['sale_date__gte'] = date_from
        if date_to is not None:
            filters['sale_date__lte'] = date_to
        db_sales = PigSaleModel.objects.prefetch_related('rows').filter(**filters)
        return [self._map_to_entity(sale) for sale in db_sales]

    def get_sale_by_id(self, sale_id: int) -> PigSaleEntity:
        db_sale = get_object_or_404(PigSaleModel.objects.prefetch_related('rows'), **self._filter_for_farm(id=sale_id))
        return self._map_to_entity(db_sale)

    def get_sale_model_by_id(self, sale_id: int) -> PigSaleModel:
        return get_object_or_404(PigSaleModel.objects.prefetch_related('rows'), **self._filter_for_farm(id=sale_id))
