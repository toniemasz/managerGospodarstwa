from dataclasses import dataclass
from datetime import date
from decimal import Decimal

@dataclass
class PigSaleEntity:
    id: int
    sale_date: date
    quantity: int
    total_weight: Decimal
    meat_class: str
    price_per_kg: Decimal

    @property
    def total_price(self) -> Decimal:
        """Kalkuluje całkowitą kwotę sprzedaży."""
        return self.total_weight * self.price_per_kg