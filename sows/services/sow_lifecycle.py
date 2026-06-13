from datetime import date, timedelta
from typing import List, Dict, Any, Optional


class SowEvent:
    def __init__(self, event_type: str, event_date: date, details: Dict[str, Any], id: int = None):
        self.id = id
        self.event_type = event_type
        self.event_date = event_date
        if isinstance(details, dict):
            self.details = details
        else:
            self.details = {}


class Sow:
    def __init__(self, id: int, ear_tag: str, entry_date: date, created_at: date, is_archived: bool = False):
        self.id = id
        self.ear_tag = ear_tag
        self.entry_date = entry_date
        self.created_at = created_at
        self.is_archived = is_archived

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

        # Listy zdarzeń pogrupowane według typów
        self.inseminations: List[SowEvent] = []
        self.pregnancy_checks: List[SowEvent] = []
        self.farrowings: List[SowEvent] = []
        self.weanings: List[SowEvent] = []
        self.vaccinations: List[SowEvent] = []

        # Pełna historia (chronologicznie od najnowszego)
        self.all_events: List[SowEvent] = []

    def load_history(self, events: List[SowEvent]) -> None:
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
        self.vaccinations = []

        for event in sorted_events:
            if event.event_type == "INSEMINATION":
                self.status = "INSEMINATED"
                self.last_insemination_date = event.event_date
                self.expected_farrowing_date = event.event_date + timedelta(days=114)
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

            elif event.event_type == "VACCINATION":
                self.vaccinations.append(event)

    def is_due_for_pregnancy_check(self, current_date: date) -> bool:
        """
        Sprawdza na podstawie bieżącej daty, czy minęło 30 dni od inseminacji
        i czy maciora wymaga wykonania badania USG lub badania szczegółowego.
        """
        if self.status in ["INSEMINATED", "TO_RECHECK"] and self.last_insemination_date:
            days_since_insemination = (current_date - self.last_insemination_date).days
            return days_since_insemination >= 30
        return False

    def get_vaccination_status(self, plan: Dict[str, Any], current_date: date) -> Dict[str, Any]:
        """
        Oblicza dynamicznie czy maciora kwalifikuje się do danego szczepienia
        na podstawie przekazanej reguły planu szczepień i bieżącej daty.

        Format struktury planu (plan):
        {
            'id': int,
            'name': str,
            'days_before_farrowing': Optional[int], # np. 21 (3 tygodnie przed porodem)
            'days_after_event': Optional[int],       # np. 14 dni po porodzie/inseminacji
            'event_source': Optional[str],           # "FARROWING" lub "INSEMINATION"
            'interval_months': Optional[int],        # cyklicznie co X miesięcy dla stada
            'reminder_days_ahead': int               # ile dni wcześniej pokazać przypomnienie
        }
        """
        target_date: Optional[date] = None
        cycle_id: str = "herd"

        # Warunek 1: Szczepienie uzależnione od planowanego oproszenia
        if plan.get('days_before_farrowing') is not None and self.expected_farrowing_date:
            target_date = self.expected_farrowing_date - timedelta(days=plan['days_before_farrowing'])
            cycle_id = f"farrowing_{self.expected_farrowing_date.strftime('%Y-%m-%d')}"

        # Warunek 2: Szczepienie po konkretnym zdarzeniu (oproszenie lub inseminacja)
        elif plan.get('days_after_event') is not None and plan.get('event_source'):
            source = plan['event_source']
            if source == "FARROWING" and self.last_farrowing_date:
                target_date = self.last_farrowing_date + timedelta(days=plan['days_after_event'])
                cycle_id = f"after_farrowing_{self.last_farrowing_date.strftime('%Y-%m-%d')}"
            elif source == "INSEMINATION" and self.last_insemination_date:
                target_date = self.last_insemination_date + timedelta(days=plan['days_after_event'])
                cycle_id = f"after_insemination_{self.last_insemination_date.strftime('%Y-%m-%d')}"

        # Warunek 3: Szczepienie cykliczne (np. co 4 miesiące od wprowadzenia do stada lub ostatniej dawki)
        elif plan.get('interval_months') is not None:
            base_date = self.entry_date or date.today()
            # Szukamy ostatniego wykonanego szczepienia o tej samej nazwie
            same_vaccinations = [v for v in self.vaccinations if v.details.get('vaccine_name') == plan['name']]
            if same_vaccinations:
                last_done = max(same_vaccinations, key=lambda x: x.event_date)
                base_date = last_done.event_date

            # Przybliżone wyliczenie kolejnego terminu (X miesięcy * 30 dni)
            target_date = base_date + timedelta(days=plan['interval_months'] * 30)
            cycle_id = f"cyclic_{target_date.strftime('%Y-%m-%d')}"

        if not target_date:
            return {'is_eligible': False, 'should_display': False, 'target_date': None, 'is_done': False}

        # Sprawdzenie, czy szczepienie w tym konkretnym cyklu zostało już zarejestrowane
        is_done = any(
            v.details.get('vaccine_name') == plan['name'] and
            (v.details.get('cycle_id') == cycle_id or abs((v.event_date - target_date).days) <= 7)
            for v in self.vaccinations
        )

        reminder_days = plan.get('reminder_days_ahead', 7)
        days_to_target = (target_date - current_date).days

        # Kwalifikuje się, jeśli nadszedł czas okna przypomnienia i nie zostało jeszcze wykonane
        should_display = (days_to_target <= reminder_days) and not is_done
        is_eligible = (days_to_target <= 0) and not is_done

        return {
            'is_eligible': is_eligible,
            'should_display': should_display,
            'target_date': target_date,
            'is_done': is_done,
            'cycle_id': cycle_id,
            'days_to_target': days_to_target
        }

    def update_state_for_date(self, current_date: date):
        """Dynamicznie aktualizuje status w pamięci na podstawie upływu czasu (30 dni)."""
        if self.status == "INSEMINATED" and self.last_insemination_date:
            if (current_date - self.last_insemination_date).days >= 30:
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

        completed_born_alive = self.total_born_alive

        if self.status == "LACTATING" and self.farrowing_count > self.weaning_count:
            if self.last_farrowing_date:
                last_farrow = next((f for f in self.farrowings if f.event_date == self.last_farrowing_date), None)
                if last_farrow:
                    completed_born_alive -= int(last_farrow.details.get("born_alive", 0))

        total_loss = completed_born_alive - self.total_weaned
        return round(max(0, total_loss) / self.weaning_count, 2)
