from dataclasses import dataclass


@dataclass(frozen=True)
class StatisticsSectionDefinition:
    key: str
    label: str
    title: str
    description: str
    dependencies: tuple[str, ...]


STATISTICS_SECTION_DEFINITIONS = (
    StatisticsSectionDefinition(
        key="profitability",
        label="Opłacalność",
        title="Opłacalność",
        description="Sprzedaż, koszty i wynik gospodarstwa w wybranym roku.",
        dependencies=("sales", "costs", "feed", "profitability"),
    ),
    StatisticsSectionDefinition(
        key="sales",
        label="Sprzedaż",
        title="Sprzedaż",
        description="Wolumen, masa i wartości dokumentów sprzedaży.",
        dependencies=("sales",),
    ),
    StatisticsSectionDefinition(
        key="sows",
        label="Maciory i rozród",
        title="Maciory i rozród",
        description="Zdarzenia rozrodcze, wyniki miotów i trendy stada.",
        dependencies=("sows",),
    ),
    StatisticsSectionDefinition(
        key="mortality",
        label="Upadki",
        title="Upadki i stan",
        description="Rozdzielone straty przed i po odsadzeniu oraz bieżący stan.",
        dependencies=("mortality",),
    ),
    StatisticsSectionDefinition(
        key="feed",
        label="Pasza i śrutowanie",
        title="Pasza i śrutowanie",
        description="Produkcja, koszt FIFO i wskaźniki wykorzystania paszy.",
        dependencies=("sales", "feed", "feed_efficiency"),
    ),
    StatisticsSectionDefinition(
        key="inventory",
        label="Magazyn",
        title="Magazyn",
        description="Bieżący stan surowców i sygnały niskiego zapasu.",
        dependencies=("inventory",),
    ),
    StatisticsSectionDefinition(
        key="costs",
        label="Koszty",
        title="Koszty",
        description="Koszt paszy i pozostałe koszty gospodarstwa bez podwójnego liczenia.",
        dependencies=("costs",),
    ),
)

STATISTICS_SECTIONS = {item.key: item for item in STATISTICS_SECTION_DEFINITIONS}
STATISTICS_SECTION_KEYS = tuple(STATISTICS_SECTIONS)
