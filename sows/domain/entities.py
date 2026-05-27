# sows/domain/entities.py
from datetime import date, timedelta
from typing import List, Dict, Any, Optional


class SowEvent:
    def __init__(self, event_type: str, event_date: date, details: Dict[str, Any], id: int = None):
        self.id = id
        self.event_type = event_type
        self.event_date = event_date
        self.details = details


class Sow:
    def __init__(self, id: int, ear_tag: str, entry_date: date, created_at: date):
        self.id = id
        self.ear_tag = ear_tag
        self.entry_date = entry_date
        self.created_at = created_at

        self.status = "IDLE"
        self.expected_farrowing_date: Optional[date] = None

        self.total_born_alive = 0
        self.total_born_dead = 0
        self.total_weaned = 0
        self.farrowing_count = 0
        self.weaning_count = 0

        self.inseminations: List[SowEvent] = []
        self.farrowings: List[SowEvent] = []
        self.weanings: List[SowEvent] = []

        self.all_events: List[SowEvent] = []

    def load_history(self, events: List[SowEvent]) -> None:
        sorted_events = sorted(events, key=lambda x: x.event_date)

        self.all_events = sorted(events, key=lambda x: x.event_date, reverse=True)

        for event in sorted_events:
            if event.event_type == "INSEMINATION":
                self.status = "INSEMINATED"
                self.expected_farrowing_date = event.event_date + timedelta(days=114)
                self.inseminations.append(event)

            elif event.event_type == "FARROWING":
                self.status = "LACTATING"
                self.expected_farrowing_date = None
                self.total_born_alive += int(event.details.get("born_alive", 0))
                self.total_born_dead += int(event.details.get("born_dead", 0))
                self.farrowing_count += 1
                self.farrowings.append(event)

            elif event.event_type == "WEANING":
                self.status = "IDLE"
                self.total_weaned += int(event.details.get("count", 0))
                self.weaning_count += 1
                self.weanings.append(event)

    def needs_vaccination(self, current_date: date) -> bool:
        if self.status != "INSEMINATED" or not self.expected_farrowing_date:
            return False
        days_until_farrowing = (self.expected_farrowing_date - current_date).days
        return 0 < days_until_farrowing <= 21

    @property
    def avg_born_alive(self) -> float:
        return round(self.total_born_alive / self.farrowing_count, 2) if self.farrowing_count else 0.0

    @property
    def avg_born_dead(self) -> float:
        return round(self.total_born_dead / self.farrowing_count, 2) if self.farrowing_count else 0.0

    @property
    def avg_weaned(self) -> float:
        return round(self.total_weaned / self.weaning_count, 2) if self.weaning_count else 0.0

    @property
    def avg_loss_before_weaning(self) -> float:
        if self.weaning_count == 0:
            return 0.0
        total_loss = self.total_born_alive - self.total_weaned
        return round(max(0, total_loss) / self.weaning_count, 2)