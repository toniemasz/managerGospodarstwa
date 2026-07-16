from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from sows.domain.rules import GESTATION_DAYS, PREGNANCY_CHECK_AFTER_DAYS


class SowEvent:
    def __init__(
        self,
        event_type: str,
        event_date: date,
        details: Dict[str, Any],
        id: int = None,
        created_at=None,
        vaccination_plan_id: int | None = None,
        vaccine_name: str = "",
        cycle_id: str = "",
        scheduled_date: date | None = None,
    ):
        self.id = id
        self.event_type = event_type
        self.event_date = event_date
        self.created_at = created_at
        self.vaccination_plan_id = vaccination_plan_id
        self.vaccine_name = vaccine_name
        self.cycle_id = cycle_id
        self.scheduled_date = scheduled_date
        if isinstance(details, dict):
            self.details = details
        else:
            self.details = {}
        self.is_piglet_transfer = False
        self.transfer_id = None

    def get_event_type_display(self) -> str:
        labels = {
            "INSEMINATION": "Inseminacja",
            "PREGNANCY_CHECK": "Badanie",
            "FARROWING": "Oproszenie",
            "WEANING": "Odsadzenie",
            "MISCARRIAGE": "Poronienie",
            "VACCINATION": "Szczepienie",
            "PIGLET_TRANSFER_OUT": "Przekazanie prosiąt",
            "PIGLET_TRANSFER_IN": "Przyjęcie prosiąt",
        }
        return labels.get(self.event_type, self.event_type)


class Sow:
    def __init__(
        self,
        id: int,
        ear_tag: str,
        entry_date: date,
        created_at: date,
        is_archived: bool = False,
        archive_reason: str = "manual",
        death_date: date | None = None,
        death_note: str = "",
    ):
        self.id = id
        self.ear_tag = ear_tag
        self.entry_date = entry_date
        self.created_at = created_at
        self.is_archived = is_archived
        self.archive_reason = archive_reason
        self.death_date = death_date
        self.death_note = death_note

        # Podstawowy status produkcyjny maciory
        self.status = "IDLE"  # Dostępne: IDLE (Jałowa), INSEMINATION (Inseminowana), PREGNANT (Prośna), TO_RECHECK (Do rebadania), LACTATING (Karmiąca)
        self.expected_farrowing_date: Optional[date] = None

        # Daty kluczowych zdarzeń w bieżącym cyklu do wyliczania alertów i szczepień
        self.last_insemination_date: Optional[date] = None
        self.last_farrowing_date: Optional[date] = None
        self.last_weaning_date: Optional[date] = None

        # Liczniki i statystyki produkcyjne
        self.total_born_alive = 0
        self.total_born_dead = 0
        self.total_weaned = 0
        self.farrowing_count = 0
        self.weaning_count = 0
        self.recorded_pre_weaning_deaths = 0

        # Listy zdarzeń pogrupowane według typów
        self.inseminations: List[SowEvent] = []
        self.pregnancy_checks: List[SowEvent] = []
        self.farrowings: List[SowEvent] = []
        self.weanings: List[SowEvent] = []
        self.miscarriages: List[SowEvent] = []
        self.vaccinations: List[SowEvent] = []

        # Pełna historia (chronologicznie od najnowszego)
        self.all_events: List[SowEvent] = []

    def load_history(self, events: List[SowEvent], gestation_days: int = GESTATION_DAYS) -> None:
        """
        Ładuje pełną historię zdarzeń maciory, odtwarzając chronologicznie jej
        bieżący status oraz agregując dane statystyczne.
        """
        sorted_events = sorted(events, key=lambda x: x.event_date)
        self.all_events = sorted(events, key=lambda x: x.event_date, reverse=True)

        # Resetowanie liczników przed ponownym przeliczeniem historii
        self.total_born_alive = 0
        self.total_born_dead = 0
        self.total_weaned = 0
        self.farrowing_count = 0
        self.weaning_count = 0

        self.inseminations = []
        self.pregnancy_checks = []
        self.farrowings = []
        self.weanings = []
        self.miscarriages = []
        self.vaccinations = []

        for event in sorted_events:
            if event.event_type == "INSEMINATION":
                self.status = "INSEMINATED"
                self.last_insemination_date = event.event_date
                self.expected_farrowing_date = event.event_date + timedelta(days=gestation_days)
                self.inseminations.append(event)

            elif event.event_type == "PREGNANCY_CHECK":
                self.pregnancy_checks.append(event)
                result = event.details.get("result")  # TAK, NIE, ?
                if result == "TAK":
                    self.status = "PREGNANT"
                elif result == "NIE":
                    self.status = "IDLE"
                    self.expected_farrowing_date = None
                elif result == "?":
                    self.status = "TO_RECHECK"

            elif event.event_type == "FARROWING":
                self.status = "LACTATING"
                self.last_farrowing_date = event.event_date
                self.expected_farrowing_date = None
                alive = event.details.get("born_alive")
                dead = event.details.get("born_dead")
                self.total_born_alive += int(alive) if alive is not None else 0
                self.total_born_dead += int(dead) if dead is not None else 0
                self.farrowing_count += 1
                self.farrowings.append(event)

            elif event.event_type == "WEANING":
                self.status = "IDLE"
                self.last_weaning_date = event.event_date
                weaned = event.details.get("count")
                self.total_weaned += int(weaned) if weaned is not None else 0
                self.weaning_count += 1
                self.weanings.append(event)

            elif event.event_type == "MISCARRIAGE":
                self.status = "IDLE"
                self.expected_farrowing_date = None
                self.miscarriages.append(event)

            elif event.event_type == "VACCINATION":
                self.vaccinations.append(event)

    def is_due_for_pregnancy_check(
        self,
        current_date: date,
        pregnancy_check_after_days: int = PREGNANCY_CHECK_AFTER_DAYS,
    ) -> bool:
        """
        Sprawdza na podstawie bieżącej daty, czy minęło 30 dni od inseminacji
        i czy maciora wymaga wykonania badania USG lub badania szczegółowego.
        """
        if self.status in ["INSEMINATED", "TO_RECHECK", "TO_CHECK"] and self.last_insemination_date:
            days_since_insemination = (current_date - self.last_insemination_date).days
            return days_since_insemination >= pregnancy_check_after_days
        return False

    def update_state_for_date(
        self,
        current_date: date,
        pregnancy_check_after_days: int = PREGNANCY_CHECK_AFTER_DAYS,
    ):
        """Dynamicznie aktualizuje status w pamięci na podstawie upływu czasu (30 dni)."""
        if self.status == "INSEMINATED" and self.last_insemination_date:
            if (current_date - self.last_insemination_date).days >= pregnancy_check_after_days:
                self.status = "TO_CHECK"

    @property
    def dynamic_status_display(self) -> str:
        """Zwraca czytelną dla człowieka nazwę aktualnego statusu."""
        if self.status == "INSEMINATED":
            return "Po inseminacji"
        elif self.status == "TO_CHECK":
            return "Do badania (USG)"
        elif self.status == "PREGNANT":
            return "Prośna (Potwierdzona)"
        elif self.status == "TO_RECHECK":
            return "Do rebadania (?)"
        elif self.status == "LACTATING":
            return "Karmiąca"
        return "Jałowa"

    @property
    def archive_reason_display(self) -> str:
        if self.archive_reason == "death":
            return "Upadek"
        return "Ręczna archiwizacja"

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
        """Średnia jawnie zarejestrowanych upadków na zarejestrowany cykl odchowu."""
        if self.farrowing_count == 0:
            return 0.0
        return round(self.recorded_pre_weaning_deaths / self.farrowing_count, 2)
