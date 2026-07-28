from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


def add_vaccination_interval(base_date: date, value: int, unit: str) -> date:
    """Dodaje interwał, zachowując kalendarzową semantykę miesięcy i lat."""
    if value < 1:
        raise ValueError("Interwał szczepienia musi być większy od zera.")
    if unit == "DAYS":
        return base_date + timedelta(days=value)
    if unit == "WEEKS":
        return base_date + timedelta(weeks=value)
    if unit == "MONTHS":
        return base_date + relativedelta(months=value)
    if unit == "YEARS":
        return base_date + relativedelta(years=value)
    raise ValueError("Nieznana jednostka interwału szczepienia.")


def vaccination_cycle_id(plan_id: int, scheduled_date: date) -> str:
    """Buduje stabilny identyfikator cyklu planu i planowanego terminu."""
    return f"periodic_{plan_id}_{scheduled_date.isoformat()}"


def first_vaccination_date_on_or_after(
    first_due_date: date,
    starts_on: date,
    value: int,
    unit: str,
) -> date:
    """Przesuwa cykl do pierwszego terminu od daty startu bez długiej pętli."""

    if first_due_date >= starts_on:
        return first_due_date
    if unit in {"DAYS", "WEEKS"}:
        step_days = value * (7 if unit == "WEEKS" else 1)
        intervals = (
            (starts_on - first_due_date).days + step_days - 1
        ) // step_days
        return first_due_date + timedelta(days=intervals * step_days)

    if unit not in {"MONTHS", "YEARS"}:
        raise ValueError("Nieznana jednostka interwału szczepienia.")

    # Najpierw stabilizujemy dzień miesiąca (np. 31.01 → 29.02 → 29.03).
    # Powtórzenie pary miesiąc/dzień oznacza, że dalszy wzorzec kalendarza
    # można bezpiecznie przeskoczyć całymi interwałami.
    target_date = first_due_date
    seen_month_days = set()
    while target_date < starts_on:
        key = (target_date.month, target_date.day)
        if target_date.day <= 28 or key in seen_month_days:
            break
        seen_month_days.add(key)
        target_date = add_vaccination_interval(target_date, value, unit)

    if target_date >= starts_on:
        return target_date

    if unit == "MONTHS":
        distance = (
            (starts_on.year - target_date.year) * 12
            + starts_on.month
            - target_date.month
        )
    else:
        distance = starts_on.year - target_date.year
    leap_intervals = max(0, distance // value - 1)
    if leap_intervals:
        target_date = add_vaccination_interval(
            target_date,
            leap_intervals * value,
            unit,
        )

    for _ in range(3):
        if target_date >= starts_on:
            return target_date
        target_date = add_vaccination_interval(target_date, value, unit)
    raise ValueError("Nie udało się wyznaczyć terminu planu od daty rozpoczęcia.")
