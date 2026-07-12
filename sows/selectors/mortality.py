from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Sum
from django.urls import reverse

from common.filter_ui import filter_ui_state, parse_filter_date
from sows.domain.mortality import calculate_pre_weaning_deaths
from sows.models import MortalityReportModel, SowEventModel, SowModel


TYPE_PRE_WEANING = "PRZED_ODSADZENIEM"


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
    """Łączy oproszenie z pierwszym odsadzeniem przed kolejnym oproszeniem."""
    events = list(
        SowEventModel.objects.filter(
            sow__farm=farm,
            event_type__in=("FARROWING", "WEANING"),
        ).select_related("sow").order_by("sow_id", "event_date", "id")
    )
    rows = []
    open_farrowing = None
    current_sow_id = None
    for event in events:
        if event.sow_id != current_sow_id:
            if open_farrowing:
                rows.append(_pre_weaning_row(open_farrowing, None))
            current_sow_id = event.sow_id
            open_farrowing = None
        if event.event_type == "FARROWING":
            if open_farrowing:
                rows.append(_pre_weaning_row(open_farrowing, None))
            open_farrowing = event
        elif open_farrowing and event.event_date >= open_farrowing.event_date:
            rows.append(_pre_weaning_row(open_farrowing, event))
            open_farrowing = None
    if open_farrowing:
        rows.append(_pre_weaning_row(open_farrowing, None))
    return rows


def _pre_weaning_row(farrowing, weaning):
    if weaning is None:
        result = calculate_pre_weaning_deaths((farrowing.details or {}).get("born_alive"), None)
        result = type(result)(None, unavailable_reason="Brak zdarzenia odsadzenia")
    else:
        result = calculate_pre_weaning_deaths(
            (farrowing.details or {}).get("born_alive"),
            (weaning.details or {}).get("count"),
        )
    return PreWeaningMortalityRow(
        sow=farrowing.sow,
        farrowing=farrowing,
        weaning=weaning,
        quantity=result.value,
        is_inconsistent=result.is_inconsistent,
        unavailable_reason=result.unavailable_reason,
    )


def mortality_list_context(farm, params) -> dict:
    mortality_type = params.get("mortality_type") or ""
    source = params.get("source") or ""
    date_from = parse_filter_date(params.get("date_from"))
    date_to = parse_filter_date(params.get("date_to"))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from

    reports = MortalityReportModel.objects.filter(farm=farm).select_related("sow", "created_by")
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
    if source == "automatic" or mortality_type == TYPE_PRE_WEANING:
        reports = reports.none()

    summary = mortality_summary(farm)
    context = {
        "mortality_reports": reports,
        "automatic_mortality_rows": automatic_rows,
        "mortality_type_choices": [
            *MortalityReportModel.TYPE_CHOICES[:1],
            (TYPE_PRE_WEANING, "Przed odsadzeniem"),
            *MortalityReportModel.TYPE_CHOICES[1:],
        ],
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
    pre_weaning = sum(row.quantity or 0 for row in cycles)
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
