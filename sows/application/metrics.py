from datetime import date, timedelta
from typing import Dict, Any, Callable, List
from sows.domain.entities import Sow

class MetricDescriptor:
    def __init__(self, key: str, display_name: str, unit: str, value_extractor: Callable[[Any], int], event_type: str):
        self.key = key
        self.display_name = display_name
        self.unit = unit
        self.value_extractor = value_extractor  # Jak wyciągnąć wartość ze szczegółów zdarzenia (details)
        self.event_type = event_type

# Jedyny rejestr w systemie. Chcesz dodać nową metrykę? Dopisujesz ją tutaj!
METRICS_REGISTRY: Dict[str, MetricDescriptor] = {
    'born_alive': MetricDescriptor(
        key='born_alive',
        display_name='Urodzenia żywe',
        unit='szt.',
        value_extractor=lambda details: int(details.get('born_alive', 0)),
        event_type='FARROWING'
    ),
    'weaned': MetricDescriptor(
        key='weaned',
        display_name='Odsadzone prosięta',
        unit='szt.',
        value_extractor=lambda details: int(details.get('count', 0)),
        event_type='WEANING'
    )
}