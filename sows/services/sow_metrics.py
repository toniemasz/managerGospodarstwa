from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class MetricDescriptor:
    key: str
    display_name: str
    unit: str
    value_extractor: Callable[[dict[str, Any]], int]
    event_type: str


METRICS_REGISTRY: dict[str, MetricDescriptor] = {
    "born_alive": MetricDescriptor(
        key="born_alive",
        display_name="Urodzenia żywe",
        unit="szt.",
        value_extractor=lambda details: int(details.get("born_alive") or 0),
        event_type="FARROWING",
    ),
    "born_dead": MetricDescriptor(
        key="born_dead",
        display_name="Urodzenia martwe",
        unit="szt.",
        value_extractor=lambda details: int(details.get("born_dead") or 0),
        event_type="FARROWING",
    ),
    "total_born": MetricDescriptor(
        key="total_born",
        display_name="Urodzenia razem",
        unit="szt.",
        value_extractor=lambda details: int(details.get("born_alive") or 0) + int(details.get("born_dead") or 0),
        event_type="FARROWING",
    ),
    "weaned": MetricDescriptor(
        key="weaned",
        display_name="Odsadzone prosięta",
        unit="szt.",
        value_extractor=lambda details: int(details.get("count") or 0),
        event_type="WEANING",
    ),
    "farrowings": MetricDescriptor(
        key="farrowings",
        display_name="Oproszenia",
        unit="zdarzeń",
        value_extractor=lambda _details: 1,
        event_type="FARROWING",
    ),
    "miscarriages": MetricDescriptor(
        key="miscarriages",
        display_name="Poronienia",
        unit="zdarzeń",
        value_extractor=lambda _details: 1,
        event_type="MISCARRIAGE",
    ),
}
