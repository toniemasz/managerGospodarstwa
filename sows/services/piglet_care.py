from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Q, Sum
from django.utils import timezone

from sows.models import MortalityReportModel, PigletTransferModel, SowEventModel


class PigletCareError(ValidationError):
    """Błąd reguły domenowej dotyczącej odchowu prosiąt."""


@dataclass(frozen=True)
class PigletCareBalance:
    farrowing: SowEventModel
    born_alive: int
    received: int
    transferred: int
    deaths: int
    weaned: int

    @property
    def available(self) -> int:
        return self.born_alive + self.received - self.transferred - self.deaths - self.weaned

    @property
    def cycle_label(self) -> str:
        return f"Maciora {self.farrowing.sow.ear_tag} · oproszenie {self.farrowing.event_date:%d.%m.%Y}"


@dataclass(frozen=True)
class PigletCareReconciliation:
    """Automatyczne rozliczenie zamkniętego odchowu na podstawie stanu faktycznego."""

    farrowing: SowEventModel
    weaning: SowEventModel
    born_alive: int
    received: int
    transferred: int
    deaths: int
    weaned: int

    @property
    def difference(self) -> int:
        return (
            self.born_alive
            + self.received
            - self.transferred
            - self.deaths
            - self.weaned
        )

    @property
    def quantity(self) -> int:
        return abs(self.difference)

    @property
    def automatic_deaths(self) -> int:
        """Upadki wyliczone z dodatniej różnicy bilansu zakończonego odchowu."""
        return max(self.difference, 0)

    @property
    def unrecorded_inflow(self) -> int:
        """Nierozpisane przyjęcie, gdy odsadzenie przewyższa stan ewidencyjny."""
        return max(-self.difference, 0)

    @property
    def is_balanced(self) -> bool:
        return self.difference == 0

    @property
    def possible_missing_outflow(self) -> int:
        """Zgodność ze starszym kontraktem: obecnie jest to automatyczny upadek."""
        return self.automatic_deaths

    @property
    def possible_missing_inflow(self) -> int:
        """Zgodność ze starszym kontraktem: nierozpisane przyjęcie."""
        return self.unrecorded_inflow

    @property
    def is_automatic_mortality(self) -> bool:
        return self.automatic_deaths > 0

    @property
    def requires_attention(self) -> bool:
        return self.unrecorded_inflow > 0

    @property
    def cycle_label(self) -> str:
        return (
            f"{self.farrowing.event_date:%d.%m.%Y} – "
            f"{self.weaning.event_date:%d.%m.%Y}"
        )

    @property
    def mortality_date(self) -> date:
        """Zgodność z filtrami listy upadków; to data kontroli, nie data upadku."""
        return self.weaning.event_date

    @property
    def sow(self):
        return self.farrowing.sow

    @property
    def explanation(self) -> str:
        if self.difference > 0:
            return (
                f"System automatycznie wyliczył {self.automatic_deaths} szt. upadków "
                "przed odsadzeniem z różnicy pomiędzy bilansem odchowu a liczbą odsadzonych."
            )
        if self.difference < 0:
            return (
                f"Odsadzono o {self.unrecorded_inflow} szt. więcej niż wynika z ewidencji. "
                "System zachował odsadzenie jako stan faktyczny i oznaczył różnicę jako "
                "nierozpisane przyjęcie prosiąt."
            )
        return "Bilans odchowu jest zgodny."


class PigletCareService:
    """Centralne źródło prawdy dla bilansu prosiąt w konkretnym odchowie."""

    def __init__(self, farm):
        if farm is None:
            raise ValueError("Obliczanie stanu odchowu wymaga jawnego gospodarstwa.")
        self.farm = farm

    def get_farrowing(self, farrowing_id: int, *, lock_for_update: bool = False) -> SowEventModel:
        queryset = SowEventModel.objects.filter(
            sow__farm=self.farm,
            event_type="FARROWING",
        ).select_related("sow")
        if lock_for_update:
            queryset = queryset.select_for_update(of=("self",))
        farrowing = queryset.filter(pk=farrowing_id).first()
        if farrowing is None:
            raise PigletCareError("Nie znaleziono oproszenia w bieżącym gospodarstwie.")
        return farrowing

    def lock_farrowings(self, farrowing_ids) -> dict[int, SowEventModel]:
        ids = sorted({int(farrowing_id) for farrowing_id in farrowing_ids})
        farrowings = list(
            SowEventModel.objects.select_for_update(of=("self",))
            .filter(
                pk__in=ids,
                sow__farm=self.farm,
                event_type="FARROWING",
            )
            .select_related("sow")
            .order_by("pk")
        )
        if len(farrowings) != len(ids):
            raise PigletCareError("Nie znaleziono wszystkich oproszeń w bieżącym gospodarstwie.")
        return {farrowing.pk: farrowing for farrowing in farrowings}

    def cycle_for_sow(
        self,
        *,
        sow,
        on_date: date,
        require_active: bool = True,
        lock_for_update: bool = False,
        excluded_weaning_id: int | None = None,
    ) -> SowEventModel:
        queryset = SowEventModel.objects.filter(
            sow=sow,
            sow__farm=self.farm,
            event_type="FARROWING",
            event_date__lte=on_date,
        ).select_related("sow").order_by("-event_date", "-id")
        farrowing = queryset.first()
        if farrowing is None:
            raise PigletCareError("Maciora nie ma oproszenia aktywnego w podanym dniu.")
        if lock_for_update:
            farrowing = self.get_farrowing(farrowing.id, lock_for_update=True)
        if require_active and not self.is_active_on(
            farrowing,
            on_date,
            excluded_weaning_id=excluded_weaning_id,
        ):
            raise PigletCareError("Odchów tej maciory był już zakończony w podanym dniu.")
        return farrowing

    def is_active_on(
        self,
        farrowing: SowEventModel,
        on_date: date,
        *,
        excluded_weaning_id: int | None = None,
    ) -> bool:
        if (
            farrowing.event_type != "FARROWING"
            or farrowing.sow.farm_id != self.farm.id
            or on_date < farrowing.event_date
        ):
            return False
        later_farrowing_exists = SowEventModel.objects.filter(
            sow_id=farrowing.sow_id,
            event_type="FARROWING",
            event_date__lte=on_date,
        ).filter(
            Q(event_date__gt=farrowing.event_date)
            | Q(event_date=farrowing.event_date, id__gt=farrowing.id)
        ).exists()
        if later_farrowing_exists:
            return False
        weanings = SowEventModel.objects.filter(
            sow_id=farrowing.sow_id,
            event_type="WEANING",
            event_date__gte=farrowing.event_date,
            event_date__lte=on_date,
        )
        if excluded_weaning_id:
            weanings = weanings.exclude(pk=excluded_weaning_id)
        return not weanings.exists()

    def active_farrowings(self, *, as_of: date | None = None) -> list[SowEventModel]:
        as_of = as_of or timezone.localdate()
        later_farrowings = SowEventModel.objects.filter(
            sow_id=OuterRef("sow_id"),
            event_type="FARROWING",
            event_date__lte=as_of,
        ).filter(
            Q(event_date__gt=OuterRef("event_date"))
            | Q(event_date=OuterRef("event_date"), id__gt=OuterRef("id"))
        )
        weanings = SowEventModel.objects.filter(
            sow_id=OuterRef("sow_id"),
            event_type="WEANING",
            event_date__gte=OuterRef("event_date"),
            event_date__lte=as_of,
        )
        return list(
            SowEventModel.objects.filter(
                sow__farm=self.farm,
                sow__is_archived=False,
                event_type="FARROWING",
                event_date__lte=as_of,
            )
            .annotate(has_later_farrowing=Exists(later_farrowings), has_weaning=Exists(weanings))
            .filter(has_later_farrowing=False, has_weaning=False)
            .select_related("sow")
            .order_by("sow__ear_tag")
        )

    def active_balances(self, *, as_of: date | None = None) -> list[PigletCareBalance]:
        as_of = as_of or timezone.localdate()
        farrowings = self.active_farrowings(as_of=as_of)
        if not farrowings:
            return []
        farrowing_ids = [farrowing.id for farrowing in farrowings]
        incoming = self._transfer_totals("target_farrowing_id", farrowing_ids, as_of)
        outgoing = self._transfer_totals("source_farrowing_id", farrowing_ids, as_of)
        deaths = dict(
            MortalityReportModel.objects.filter(
                farm=self.farm,
                mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
                farrowing_id__in=farrowing_ids,
                mortality_date__lte=as_of,
            )
            .values_list("farrowing_id")
            .annotate(total=Sum("quantity"))
        )
        return [
            PigletCareBalance(
                farrowing=farrowing,
                born_alive=self._born_alive(farrowing),
                received=incoming.get(farrowing.id, 0),
                transferred=outgoing.get(farrowing.id, 0),
                deaths=deaths.get(farrowing.id, 0) or 0,
                weaned=0,
            )
            for farrowing in farrowings
        ]

    def current_balance_for_sow(self, sow, *, as_of: date | None = None) -> PigletCareBalance | None:
        as_of = as_of or timezone.localdate()
        try:
            farrowing = self.cycle_for_sow(sow=sow, on_date=as_of, require_active=True)
        except PigletCareError:
            return None
        return self.balance(farrowing, as_of=as_of)

    def balance(
        self,
        farrowing: SowEventModel,
        *,
        as_of: date | None = None,
        excluded_transfer_id: int | None = None,
        excluded_mortality_id: int | None = None,
        excluded_weaning_id: int | None = None,
    ) -> PigletCareBalance:
        as_of = as_of or date.max
        transfers = PigletTransferModel.objects.filter(
            farm=self.farm,
            canceled_at__isnull=True,
            transfer_date__lte=as_of,
        )
        if excluded_transfer_id:
            transfers = transfers.exclude(pk=excluded_transfer_id)
        received = transfers.filter(target_farrowing=farrowing).aggregate(total=Sum("quantity"))["total"] or 0
        transferred = transfers.filter(source_farrowing=farrowing).aggregate(total=Sum("quantity"))["total"] or 0
        mortalities = MortalityReportModel.objects.filter(
            farm=self.farm,
            farrowing=farrowing,
            mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
            mortality_date__lte=as_of,
        )
        if excluded_mortality_id:
            mortalities = mortalities.exclude(pk=excluded_mortality_id)
        deaths = mortalities.aggregate(total=Sum("quantity"))["total"] or 0
        weanings = self.weanings_for_cycle(farrowing).filter(event_date__lte=as_of)
        if excluded_weaning_id:
            weanings = weanings.exclude(pk=excluded_weaning_id)
        weaned = sum(self._detail_count(details, "count") for details in weanings.values_list("details", flat=True))
        return PigletCareBalance(
            farrowing=farrowing,
            born_alive=self._born_alive(farrowing),
            received=received,
            transferred=transferred,
            deaths=deaths,
            weaned=weaned,
        )

    def validate_transfer(
        self,
        *,
        source_farrowing: SowEventModel,
        target_farrowing: SowEventModel,
        quantity: int,
        transfer_date: date,
        replaced_transfer: PigletTransferModel | None = None,
    ) -> None:
        if quantity is None or quantity <= 0:
            raise PigletCareError("Liczba przenoszonych prosiąt musi być większa od zera.")
        if source_farrowing.id == target_farrowing.id or source_farrowing.sow_id == target_farrowing.sow_id:
            raise PigletCareError("Maciora źródłowa i docelowa muszą być różne.")
        if source_farrowing.sow.farm_id != self.farm.id or target_farrowing.sow.farm_id != self.farm.id:
            raise PigletCareError("Oba odchowy muszą należeć do bieżącego gospodarstwa.")
        if not self.is_active_on(source_farrowing, transfer_date):
            raise PigletCareError("Odchów źródłowy nie był aktywny w dniu przeniesienia.")
        if not self.is_active_on(target_farrowing, transfer_date):
            raise PigletCareError("Odchów docelowy nie był aktywny w dniu przeniesienia.")

        candidate = PigletTransferModel(
            farm=self.farm,
            source_farrowing=source_farrowing,
            target_farrowing=target_farrowing,
            quantity=quantity,
            transfer_date=transfer_date,
        )
        excluded_ids = {replaced_transfer.id} if replaced_transfer else set()
        affected = {
            source_farrowing.id: source_farrowing,
            target_farrowing.id: target_farrowing,
        }
        if replaced_transfer:
            affected[replaced_transfer.source_farrowing_id] = replaced_transfer.source_farrowing
            affected[replaced_transfer.target_farrowing_id] = replaced_transfer.target_farrowing
        for farrowing in affected.values():
            self.validate_cycle_history(
                farrowing,
                excluded_transfer_ids=excluded_ids,
                candidate_transfers=[candidate],
            )

    def validate_transfer_cancellation(self, transfer: PigletTransferModel) -> None:
        for farrowing in (transfer.source_farrowing, transfer.target_farrowing):
            self.validate_cycle_history(farrowing, excluded_transfer_ids={transfer.id})

    def validate_pre_weaning_mortality(
        self,
        *,
        farrowing: SowEventModel,
        mortality_date: date,
        quantity: int,
        replaced_report: MortalityReportModel | None = None,
    ) -> None:
        excluded_report_id = replaced_report.id if replaced_report else None
        if quantity is None or quantity <= 0:
            raise PigletCareError("Liczba upadków musi być większa od zera.")
        if not self.is_active_on(farrowing, mortality_date):
            raise PigletCareError("Odchów nie był aktywny w dniu upadku.")
        candidate = MortalityReportModel(
            farm=self.farm,
            mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
            sow=farrowing.sow,
            farrowing=farrowing,
            mortality_date=mortality_date,
            quantity=quantity,
        )
        self.validate_cycle_history(
            farrowing,
            excluded_mortality_ids={excluded_report_id} if excluded_report_id else set(),
            candidate_mortalities=[candidate],
        )

    def validate_weaning(
        self,
        *,
        sow,
        weaning_date: date,
        quantity: int,
        replaced_weaning: SowEventModel | None = None,
        lock_for_update: bool = False,
    ) -> PigletCareBalance:
        """Waliduje dane podstawowe; rozbieżność bilansu nie blokuje odsadzenia."""
        if quantity is None or quantity < 0:
            raise PigletCareError("Liczba odsadzanych prosiąt nie może być ujemna.")
        excluded_weaning_id = replaced_weaning.id if replaced_weaning else None
        farrowing = self.cycle_for_sow(
            sow=sow,
            on_date=weaning_date,
            require_active=True,
            lock_for_update=lock_for_update,
            excluded_weaning_id=excluded_weaning_id,
        )
        balance = self.balance(
            farrowing,
            as_of=weaning_date,
            excluded_weaning_id=excluded_weaning_id,
        )
        return balance

    def completed_cycle_reconciliations(
        self,
        *,
        sow_id: int | None = None,
        weaned_from: date | None = None,
        include_balanced: bool = False,
    ) -> list[PigletCareReconciliation]:
        """Wylicza upadki lub nierozpisane przyjęcie dla zakończonych odchowów."""
        events = SowEventModel.objects.filter(
            sow__farm=self.farm,
            event_type__in=("FARROWING", "WEANING"),
        )
        if sow_id is not None:
            events = events.filter(sow_id=sow_id)
        events = list(events.select_related("sow").order_by("sow_id", "event_date", "id"))

        cycles = []
        current_farrowing = None
        current_weanings = []
        current_sow_id = None

        def append_cycle() -> None:
            if current_farrowing is not None and current_weanings:
                cycles.append((current_farrowing, list(current_weanings)))

        for event in events:
            if event.sow_id != current_sow_id:
                append_cycle()
                current_sow_id = event.sow_id
                current_farrowing = None
                current_weanings = []
            if event.event_type == "FARROWING":
                append_cycle()
                current_farrowing = event
                current_weanings = []
            elif current_farrowing is not None:
                current_weanings.append(event)
        append_cycle()

        if weaned_from is not None:
            cycles = [
                (farrowing, weanings)
                for farrowing, weanings in cycles
                if weanings[-1].event_date >= weaned_from
            ]
        if not cycles:
            return []

        farrowing_ids = [farrowing.id for farrowing, _weanings in cycles]
        farrowing_id_set = set(farrowing_ids)
        cycle_end_by_farrowing_id = {
            farrowing.id: weanings[-1].event_date
            for farrowing, weanings in cycles
        }
        incoming = defaultdict(int)
        outgoing = defaultdict(int)
        for transfer in PigletTransferModel.objects.filter(
            farm=self.farm,
            canceled_at__isnull=True,
        ).filter(
            Q(source_farrowing_id__in=farrowing_ids)
            | Q(target_farrowing_id__in=farrowing_ids)
        ):
            if (
                transfer.source_farrowing_id in farrowing_id_set
                and transfer.transfer_date
                <= cycle_end_by_farrowing_id[transfer.source_farrowing_id]
            ):
                outgoing[transfer.source_farrowing_id] += transfer.quantity
            if (
                transfer.target_farrowing_id in farrowing_id_set
                and transfer.transfer_date
                <= cycle_end_by_farrowing_id[transfer.target_farrowing_id]
            ):
                incoming[transfer.target_farrowing_id] += transfer.quantity
        deaths = defaultdict(int)
        for farrowing_id, mortality_date, quantity in (
            MortalityReportModel.objects.filter(
                farm=self.farm,
                mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
                farrowing_id__in=farrowing_ids,
            ).values_list("farrowing_id", "mortality_date", "quantity")
        ):
            if mortality_date <= cycle_end_by_farrowing_id[farrowing_id]:
                deaths[farrowing_id] += quantity

        reconciliations = []
        for farrowing, weanings in cycles:
            row = PigletCareReconciliation(
                farrowing=farrowing,
                weaning=weanings[-1],
                born_alive=self._born_alive(farrowing),
                received=incoming[farrowing.id],
                transferred=outgoing[farrowing.id],
                deaths=deaths.get(farrowing.id, 0) or 0,
                weaned=sum(
                    self._detail_count(weaning.details, "count")
                    for weaning in weanings
                ),
            )
            if include_balanced or not row.is_balanced:
                reconciliations.append(row)
        return sorted(
            reconciliations,
            key=lambda row: (row.weaning.event_date, row.weaning.id),
            reverse=True,
        )

    def validate_cycle_history(
        self,
        farrowing: SowEventModel,
        *,
        excluded_transfer_ids: set[int] | None = None,
        candidate_transfers: list[PigletTransferModel] | None = None,
        excluded_mortality_ids: set[int] | None = None,
        candidate_mortalities: list[MortalityReportModel] | None = None,
        excluded_weaning_ids: set[int] | None = None,
        candidate_weanings: list[SowEventModel] | None = None,
        born_alive_override: int | None = None,
    ) -> None:
        deltas = defaultdict(int)
        dated_weanings = defaultdict(list)
        transfers = PigletTransferModel.objects.filter(
            farm=self.farm,
            canceled_at__isnull=True,
        ).filter(Q(source_farrowing=farrowing) | Q(target_farrowing=farrowing))
        if excluded_transfer_ids:
            transfers = transfers.exclude(pk__in=excluded_transfer_ids)
        for transfer in transfers:
            if transfer.source_farrowing_id == farrowing.id:
                deltas[transfer.transfer_date] -= transfer.quantity
            if transfer.target_farrowing_id == farrowing.id:
                deltas[transfer.transfer_date] += transfer.quantity
        for transfer in candidate_transfers or []:
            if transfer.source_farrowing_id == farrowing.id:
                deltas[transfer.transfer_date] -= transfer.quantity
            if transfer.target_farrowing_id == farrowing.id:
                deltas[transfer.transfer_date] += transfer.quantity

        mortalities = MortalityReportModel.objects.filter(
            farm=self.farm,
            farrowing=farrowing,
            mortality_type=MortalityReportModel.TYPE_PRE_WEANING,
        )
        if excluded_mortality_ids:
            mortalities = mortalities.exclude(pk__in=excluded_mortality_ids)
        for mortality_date, quantity in mortalities.values_list("mortality_date", "quantity"):
            deltas[mortality_date] -= quantity
        for report in candidate_mortalities or []:
            if report.farrowing_id == farrowing.id:
                deltas[report.mortality_date] -= report.quantity

        weanings = self.weanings_for_cycle(farrowing)
        if excluded_weaning_ids:
            weanings = weanings.exclude(pk__in=excluded_weaning_ids)
        for weaning_date, details in weanings.values_list("event_date", "details"):
            dated_weanings[weaning_date].append(
                self._detail_count(details, "count")
            )
        for event in candidate_weanings or []:
            if event.sow_id == farrowing.sow_id:
                dated_weanings[event.event_date].append(
                    self._detail_count(event.details, "count")
                )

        available = self._born_alive(farrowing) if born_alive_override is None else born_alive_override
        for operation_date in sorted(set(deltas) | set(dated_weanings)):
            available += deltas[operation_date]
            if available < 0:
                raise PigletCareError(
                    "Operacja spowodowałaby ujemny stan odchowu "
                    f"maciory {farrowing.sow.ear_tag} w dniu {operation_date:%d.%m.%Y}."
                )
            for quantity in dated_weanings[operation_date]:
                available -= quantity
                # Odsadzenie jest stanem faktycznym zamykającym odchów.
                # Dodatnia różnica staje się automatycznym upadkiem, a ujemna
                # nierozpisanym przyjęciem. Żaden z tych przypadków nie blokuje
                # produkcji ani nie tworzy fikcyjnego transferu.
                available = 0

    def weanings_for_cycle(self, farrowing: SowEventModel):
        queryset = SowEventModel.objects.filter(
            sow_id=farrowing.sow_id,
            event_type="WEANING",
            event_date__gte=farrowing.event_date,
        )
        next_farrowing = SowEventModel.objects.filter(
            sow_id=farrowing.sow_id,
            event_type="FARROWING",
        ).filter(
            Q(event_date__gt=farrowing.event_date)
            | Q(event_date=farrowing.event_date, id__gt=farrowing.id)
        ).order_by("event_date", "id").first()
        if next_farrowing:
            queryset = queryset.filter(event_date__lt=next_farrowing.event_date)
        return queryset

    def _transfer_totals(self, field_name: str, farrowing_ids: list[int], as_of: date) -> dict[int, int]:
        return {
            farrowing_id: total or 0
            for farrowing_id, total in (
                PigletTransferModel.objects.filter(
                    farm=self.farm,
                    canceled_at__isnull=True,
                    transfer_date__lte=as_of,
                    **{f"{field_name}__in": farrowing_ids},
                )
                .values_list(field_name)
                .annotate(total=Sum("quantity"))
            )
        }

    @staticmethod
    def _detail_count(details, key: str) -> int:
        try:
            return int((details or {}).get(key) or 0)
        except (TypeError, ValueError):
            return 0

    def _born_alive(self, farrowing: SowEventModel) -> int:
        return self._detail_count(farrowing.details, "born_alive")
