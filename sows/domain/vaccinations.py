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
