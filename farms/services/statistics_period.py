from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class StatisticsPeriod:
    """Jawny zakres danych okresowych używany przez raporty gospodarstwa."""

    date_from: date | None = None
    date_to: date | None = None

    def __post_init__(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Początek okresu statystyk nie może być późniejszy niż koniec.")

    @classmethod
    def from_dates(cls, *, date_from=None, date_to=None):
        return cls(date_from=date_from, date_to=date_to)

    @property
    def cache_parts(self) -> tuple:
        return self.date_from, self.date_to
