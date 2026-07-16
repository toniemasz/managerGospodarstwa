from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PreWeaningMortalityCalculation:
    value: int | None
    is_inconsistent: bool = False
    unavailable_reason: str = ""


def calculate_pre_weaning_deaths(born_alive, weaned_count) -> PreWeaningMortalityCalculation:
    """Oblicza wyłącznie historyczny szacunek dla cykli sprzed jawnego rejestru upadków."""
    if born_alive in (None, ""):
        return PreWeaningMortalityCalculation(None, unavailable_reason="Brak liczby urodzonych żywych")
    if weaned_count in (None, ""):
        return PreWeaningMortalityCalculation(None, unavailable_reason="Brak liczby odsadzonych")
    try:
        born_alive = int(born_alive)
        weaned_count = int(weaned_count)
    except (TypeError, ValueError):
        return PreWeaningMortalityCalculation(None, unavailable_reason="Nieprawidłowe dane cyklu")
    inconsistent = weaned_count > born_alive
    return PreWeaningMortalityCalculation(
        value=max(born_alive - weaned_count, 0),
        is_inconsistent=inconsistent,
    )
