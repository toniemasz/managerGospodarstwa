from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Sum
from django.urls import reverse

from common.filter_ui import filter_ui_state, parse_filter_date
from sows.domain.mortality import calculate_pre_weaning_deaths
from sows.models import MortalityReportModel, PigletTransferModel, SowEventModel, SowModel


TYPE_PRE_WEANING = MortalityReportModel.TYPE_PRE_WEANING


@dataclass(frozen=True)
class PreWeaningMortalityRow:
    sow: SowModel
    farrowing: SowEventModel
    weaning: SowEventModel | None
    quantity: int | None
    is_inconsistent: bool
    unavailable_reason: str

    @property
    def mortality_date(self) -> date:
        return self.weaning.event_date if self.weaning else self.farrowing.event_date

    @property
    def cycle_label(self) -> str:
        end = self.weaning.event_date.strftime("%d.%m.%Y") if self.weaning else "brak odsadzenia"
        return f"{self.farrowing.event_date:%d.%m.%Y} – {end}"


def pre_weaning_mortality_cycles(farm) -> list[PreWeaningMortalityRow]:
    """Zwraca legacy szacunki tylko dla cykli bez jawnych upadków i transferów."""
    events = list(
        SowEventModel.objects.filter(
            sow__farm=farm,
            event_type__in=("FARROWING", "WEANING"),
        ).select_related("sow").order_by("sow_id", "event_date", "id")
    )
    rows = []
    open_farrowing = None
    cycle_weanings = []
    current_sow_id = None

    def append_open_cycle():
        if open_farrowing:
            rows.append(_pre_weaning_row(open_farrowing, cycle_weanings))

    for event in events:
        if event.sow_id != current_sow_id:
            append_open_cycle()
            current_sow_id = event.sow_id
            open_farrowing = None
            cycle_weanings = []
        if event.event_type == "FARROWING":
            append_open_cycle()
            open_farrowing = event
            cycle_weanings = []
        elif open_farrowing and event.event_date >= open_farrowing.event_date:
            cycle_weanings.append(event)
    append_open_cycle()
    explicitly_tracked_ids = set(
        MortalityReportModel.objects.filter(
            farm=farm,
            mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
            farrowing__isnull=False,
        ).values_list("farrowing_id", flat=True)
    )
    transfer_cycle_ids = set(
        PigletTransferModel.objects.filter(farm=farm, canceled_at__isnull=True)
        .values_list("source_farrowing_id", flat=True)
    ) | set(
        PigletTransferModel.objects.filter(farm=farm, canceled_at__isnull=True)
        .values_list("target_farrowing_id", flat=True)
    )
    return [
        row for row in rows
        if row.farrowing.id not in explicitly_tracked_ids | transfer_cycle_ids
    ]


def _pre_weaning_row(farrowing, weanings):
    weaning = weanings[-1] if weanings else None
    if not weanings:
        result = calculate_pre_weaning_deaths((farrowing.details or {}).get("born_alive"), None)
        result = type(result)(None, unavailable_reason="Brak zdarzenia odsadzenia")
    else:
        result = calculate_pre_weaning_deaths(
            (farrowing.details or {}).get("born_alive"),
            _sum_weaned(weanings),
        )
    return PreWeaningMortalityRow(
        sow=farrowing.sow,
        farrowing=farrowing,
        weaning=weaning,
        quantity=result.value,
        is_inconsistent=result.is_inconsistent,
        unavailable_reason=result.unavailable_reason,
    )


def _sum_weaned(weanings):
    total = 0
    for weaning in weanings:
        value = (weaning.details or {}).get("count")
        if value in (None, ""):
            return None
        try:
            total += int(value)
        except (TypeError, ValueError):
            return "nieprawidłowe"
    return total


def mortality_list_context(farm, params) -> dict:
    mortality_type = params.get("mortality_type") or ""
    source = params.get("source") or ""
    date_from = parse_filter_date(params.get("date_from"))
    date_to = parse_filter_date(params.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    reports = MortalityReportModel.objects.filter(farm=farm).select_related("sow", "farrowing", "created_by")
    if mortality_type in {value for value, _label in MortalityReportModel.TYPE_CHOICES}:
        reports = reports.filter(mortality_type=mortality_type)
    if date_from:
        reports = reports.filter(mortality_date__gte=date_from)
    if date_to:
        reports = reports.filter(mortality_date__lte=date_to)
    if params.get("reason"):
        reports = reports.filter(reason__icontains=params["reason"].strip())
    if params.get("sow"):
        reports = reports.filter(sow__ear_tag__icontains=params["sow"].strip())

    automatic_rows = pre_weaning_mortality_cycles(farm)
    if date_from:
        automatic_rows = [row for row in automatic_rows if row.mortality_date >= date_from]
    if date_to:
        automatic_rows = [row for row in automatic_rows if row.mortality_date <= date_to]
    if params.get("sow"):
        needle = params["sow"].strip().casefold()
        automatic_rows = [row for row in automatic_rows if needle in row.sow.ear_tag.casefold()]
    if params.get("cycle"):
        needle = params["cycle"].strip().casefold()
        automatic_rows = [row for row in automatic_rows if needle in row.cycle_label.casefold()]
    if source == "manual" or (mortality_type and mortality_type != TYPE_PRE_WEANING):
        automatic_rows = []
    if source == "automatic":
        reports = reports.none()

    summary = mortality_summary(farm)
    context = {
        "mortality_reports": reports,
        "automatic_mortality_rows": automatic_rows,
        "mortality_type_choices": MortalityReportModel.TYPE_CHOICES,
        "selected_mortality_type": mortality_type,
        "selected_source": source,
        "date_from": date_from,
        "date_to": date_to,
        "summary": summary,
        "post_weaning_stock": post_weaning_stock_summary(farm),
    }
    context.update(filter_ui_state(params, {
        "mortality_type": "Typ", "source": "Źródło", "date_from": "Od", "date_to": "Do",
        "reason": "Przyczyna", "sow": "Maciora", "cycle": "Cykl",
    }))
    context["filter_clear_url"] = reverse("mortality_list")
    return context


def mortality_summary(farm, *, date_from=None, date_to=None) -> dict:
    reports = MortalityReportModel.objects.filter(farm=farm)
    if date_from:
        reports = reports.filter(mortality_date__gte=date_from)
    if date_to:
        reports = reports.filter(mortality_date__lte=date_to)
    quantities = dict(
        reports
        .values_list("mortality_type").annotate(total=Sum("quantity"))
    )
    cycles = pre_weaning_mortality_cycles(farm)
    if date_from:
        cycles = [row for row in cycles if row.mortality_date >= date_from]
    if date_to:
        cycles = [row for row in cycles if row.mortality_date <= date_to]
    pre_weaning = (
        quantities.get(MortalityReportModel.TYPE_PRE_WEANING, 0) or 0
    ) + sum(row.quantity or 0 for row in cycles)
    post_weaning = sum(quantities.get(kind, 0) or 0 for kind in MortalityReportModel.POST_WEANING_TYPES)
    return {
        "sow": quantities.get(MortalityReportModel.TYPE_SOW, 0) or 0,
        "pre_weaning": pre_weaning,
        "piglet": quantities.get(MortalityReportModel.TYPE_PIGLET, 0) or 0,
        "weaner": quantities.get(MortalityReportModel.TYPE_WEANER, 0) or 0,
        "finisher": quantities.get(MortalityReportModel.TYPE_FINISHER, 0) or 0,
        "unspecified": quantities.get(MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING, 0) or 0,
        "post_weaning": post_weaning,
    }


def post_weaning_stock_summary(farm) -> dict:
    weaned_total = _sum_weaned_animals(farm)
    mortality_total = (
        MortalityReportModel.objects.filter(
            farm=farm,
            mortality_type__in=MortalityReportModel.POST_WEANING_TYPES,
        ).aggregate(total=Sum("quantity"))["total"] or 0
    )
    return {
        "weaned_total": weaned_total,
        "mortality_total": mortality_total,
        "current_stock": max(0, weaned_total - mortality_total),
    }


def _sum_weaned_animals(farm) -> int:
    total = 0
    for details in SowEventModel.objects.filter(sow__farm=farm, event_type="WEANING").values_list("details", flat=True):
        try:
            total += int((details or {}).get("count") or 0)
        except (TypeError, ValueError):
            continue
    return total
