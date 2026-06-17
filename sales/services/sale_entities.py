from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass
class PigSaleEntity:
    id: int
    sale_date: date | None
    quantity: int
    total_weight: Decimal
    meat_class: str
    price_per_kg: Decimal
    document_number: str = ''
    no_settlement: bool = False
    settlement_status: str = ''
    avg_meatiness_seurop: Decimal | None = None
    live_weight: Decimal | None = None
    dressing_percentage: Decimal | None = None
    net_value: Decimal = Decimal('0.00')
    gross_value: Decimal = Decimal('0.00')

    @property
    def net_price(self) -> Decimal:
        if self.net_value:
            return self.net_value
        return self.total_weight * self.price_per_kg

    @property
    def total_price(self) -> Decimal:
        """Kalkuluje całkowitą kwotę sprzedaży."""
        if self.gross_value:
            return self.gross_value
        return self.total_weight * self.price_per_kg
