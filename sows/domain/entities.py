# sows/domain/entities.py
from datetime import date, timedelta
from typing import List, Dict, Any, Optional



class SowEvent:
    """Reprezentacja pojedynczego wiersza z tabeli zdarzeń w Supabase"""

    def __init__(self, event_type: str, event_date: date, details: Dict[str, Any]):
        self.event_type = event_type
        self.event_date = event_date
        self.details = details


class Sow:
    def __init__(self, sow_id: str, ear_tag: str, birth_date: date):
        self.sow_id = sow_id
        self.ear_tag = ear_tag
        self.birth_date = birth_date

        self.status = "IDLE"
        self.expected_farrowing_date: Optional[date] = None

        self.total_born_alive = 0
        self.total_weaned = 0

    def load_history(self, events: List[SowEvent]) -> None:
        """Przetwarza historię zdarzeń chronologicznie, budując aktualny stan lochy"""
        sorted_events = sorted(events, key=lambda x: x.event_date)

        for event in sorted_events:
            if event.event_type == "INSEMINATION":
                self.status = "INSEMINATED"
                self.expected_farrowing_date = event.event_date + timedelta(days=114)

            elif event.event_type == "FARROWING":
                self.status = "LACTATING"
                self.expected_farrowing_date = None
                self.total_born_alive += event.details.get("born_alive", 0)

            elif event.event_type == "WEANING":
                self.status = "IDLE"
                self.total_weaned += event.details.get("count", 0)

    def needs_vaccination(self, current_date: date) -> bool:
        """Alert: Zwraca True, jeśli locha jest w okresie 3 tygodni przed porodem"""

        if self.status != "INSEMINATED" or not self.expected_farrowing_date:
            return False

        days_until_farrowing = (self.expected_farrowing_date - current_date).days

        return 0 < days_until_farrowing <= 21