from sales.selectors import sale_for_farm, sales_for_farm


class SaleRepository:
    def __init__(self, farm):
        if farm is None:
            raise ValueError("Repozytorium sprzedaży wymaga jawnego gospodarstwa.")
        self.farm = farm

    def get_all_sales(self):
        """Kompatybilne wejście; nowy kod powinien używać `sales_for_farm`."""

        return list(sales_for_farm(self.farm))

    def get_sales_between(self, date_from=None, date_to=None):
        return list(
            sales_for_farm(
                self.farm,
                date_from=date_from,
                date_to=date_to,
            )
        )

    def get_sale_by_id(self, sale_id: int):
        return sale_for_farm(self.farm, sale_id, with_rows=True)

    def get_sale_model_by_id(self, sale_id: int):
        return sale_for_farm(self.farm, sale_id, with_rows=True)
