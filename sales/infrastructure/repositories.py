from typing import List
from django.shortcuts import get_object_or_404
from sales.models import PigSaleModel
from sales.domain.entities import PigSaleEntity

class SaleRepository:
    def _map_to_domain(self, db_model: PigSaleModel) -> PigSaleEntity:
        return PigSaleEntity(
            id=db_model.id,
            sale_date=db_model.sale_date,
            quantity=db_model.quantity,
            total_weight=db_model.total_weight,
            meat_class=db_model.meat_class,
            price_per_kg=db_model.price_per_kg
        )

    def get_all_sales(self) -> List[PigSaleEntity]:
        db_sales = PigSaleModel.objects.all()
        return [self._map_to_domain(sale) for sale in db_sales]

    def get_sale_by_id(self, sale_id: int) -> PigSaleEntity:
        db_sale = get_object_or_404(PigSaleModel, id=sale_id)
        return self._map_to_domain(db_sale)