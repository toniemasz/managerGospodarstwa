from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from common.money import quantize_money, quantize_price
from costs.actions import sync_production_cost
from feed.actions.finished_feed import create_finished_feed_batch_for_production
from feed.domain.production import ProductionCostResult
from feed.models import (
    FeedProductModel,
    FeedServingAllocationModel,
    FinishedFeedBatchModel,
    ProductionIngredientUsageModel,
    ProductionModel,
)


@dataclass(frozen=True)
class IntegrityIssue:
    code: str
    object_label: str
    object_id: int | None
    message: str
    repairable: bool = False


@dataclass
class IntegrityAuditResult:
    issues: list[IntegrityIssue] = field(default_factory=list)
    repaired: int = 0

    @property
    def issue_count(self) -> int:
        return len(self.issues)


class FeedIntegrityService:
    """Audytuje dane paszowe; zapis wykonuje wyłącznie po jawnym ``apply=True``."""

    def __init__(self, farm):
        if farm is None:
            raise ValueError("Audyt integralności wymaga jawnego gospodarstwa.")
        self.farm = farm

    def audit(self, *, apply: bool = False) -> IntegrityAuditResult:
        if apply:
            with transaction.atomic():
                return self._audit(apply=True)
        return self._audit(apply=False)

    def _audit(self, *, apply: bool) -> IntegrityAuditResult:
        result = IntegrityAuditResult()
        productions = ProductionModel.objects.filter(
            recipe__farm=self.farm,
            status=ProductionModel.Statuses.COMPLETED,
        ).select_related("recipe", "cost_entry", "finished_feed_batch")
        if apply:
            productions = productions.select_for_update()

        for production in productions.order_by("date", "time", "id"):
            self._audit_production(production, result, apply=apply)

        self._audit_batch_balances(result, apply=apply)
        self._audit_product_sources(result)
        self._audit_cross_farm_relations(result)
        return result

    def _audit_production(self, production, result: IntegrityAuditResult, *, apply: bool) -> None:
        usages = ProductionIngredientUsageModel.objects.filter(
            farm=self.farm,
            production=production,
        )
        fifo_total = quantize_money(usages.aggregate(total=Sum("cost"))["total"] or Decimal("0.00"))
        cost_per_kg = quantize_price(fifo_total / production.quantity_kg) if production.quantity_kg else Decimal("0.00000")
        cost_entry = getattr(production, "cost_entry", None)
        batch = getattr(production, "finished_feed_batch", None)
        mismatch = (
            production.feed_cost_total != fifo_total
            or production.feed_cost_per_kg != cost_per_kg
            or cost_entry is None
            or (cost_entry is not None and cost_entry.amount != fifo_total)
            or batch is None
            or (batch is not None and (batch.total_cost != fifo_total or batch.cost_per_kg != cost_per_kg))
        )
        if not mismatch:
            return
        result.issues.append(IntegrityIssue(
            code="PRODUCTION_COST_MISMATCH",
            object_label=production._meta.label,
            object_id=production.pk,
            message="Koszt FIFO, snapshot, rejestr kosztów lub partia gotowej paszy są niespójne.",
            repairable=True,
        ))
        if not apply:
            return
        ProductionModel.objects.filter(pk=production.pk).update(
            feed_cost_total=fifo_total,
            feed_cost_per_kg=cost_per_kg,
        )
        production.feed_cost_total = fifo_total
        production.feed_cost_per_kg = cost_per_kg
        cost_result = ProductionCostResult(
            total_cost=fifo_total,
            cost_per_kg=cost_per_kg,
            is_partial=production.feed_cost_is_partial,
            missing_components=tuple(filter(None, (production.feed_cost_note,))),
            usage_count=usages.count(),
        )
        sync_production_cost(farm=self.farm, production=production, cost_result=cost_result)
        create_finished_feed_batch_for_production(production)
        result.repaired += 1

    def _audit_batch_balances(self, result: IntegrityAuditResult, *, apply: bool) -> None:
        batches = FinishedFeedBatchModel.objects.filter(farm=self.farm).order_by("id")
        if apply:
            batches = batches.select_for_update()
        for batch in batches:
            allocated = FeedServingAllocationModel.objects.filter(batch=batch).aggregate(
                total=Sum("quantity_kg"),
            )["total"] or Decimal("0.00")
            expected_remaining = batch.initial_quantity_kg - allocated
            if expected_remaining == batch.remaining_quantity_kg:
                continue
            repairable = Decimal("0.00") <= expected_remaining <= batch.initial_quantity_kg
            result.issues.append(IntegrityIssue(
                code="FINISHED_BATCH_BALANCE",
                object_label=batch._meta.label,
                object_id=batch.pk,
                message=(
                    f"Stan partii {batch.remaining_quantity_kg} kg nie odpowiada "
                    f"ilości początkowej minus alokacje ({expected_remaining} kg)."
                ),
                repairable=repairable,
            ))
            if apply and repairable:
                FinishedFeedBatchModel.objects.filter(pk=batch.pk).update(
                    remaining_quantity_kg=expected_remaining,
                )
                result.repaired += 1

    def _audit_product_sources(self, result: IntegrityAuditResult) -> None:
        products = FeedProductModel.objects.filter(farm=self.farm).prefetch_related("batches")
        for product in products:
            has_production = product.batches.filter(production__isnull=False).exists()
            has_purchase = product.batches.filter(ready_feed_delivery__isnull=False).exists()
            expected = None
            if has_production and not has_purchase:
                expected = FeedProductModel.SourceTypes.PRODUCED
            elif has_purchase and not has_production:
                expected = FeedProductModel.SourceTypes.PURCHASED_READY
            if expected and product.source_type != expected:
                result.issues.append(IntegrityIssue(
                    code="FEED_PRODUCT_SOURCE",
                    object_label=product._meta.label,
                    object_id=product.pk,
                    message=f"Typ produktu {product.source_type} nie odpowiada jego źródłu {expected}.",
                    repairable=False,
                ))
            if has_production and has_purchase:
                result.issues.append(IntegrityIssue(
                    code="FEED_PRODUCT_SOURCE_CONFLICT",
                    object_label=product._meta.label,
                    object_id=product.pk,
                    message="Produkt ma jednocześnie partie z zakupu i produkcji; wymaga kontrolowanego rozdzielenia.",
                    repairable=False,
                ))

    def _audit_cross_farm_relations(self, result: IntegrityAuditResult) -> None:
        cross_farm_usages = ProductionIngredientUsageModel.objects.filter(farm=self.farm).exclude(
            production__recipe__farm=self.farm,
        ).count()
        cross_farm_batches = FinishedFeedBatchModel.objects.filter(farm=self.farm).exclude(
            product__farm=self.farm,
        ).count()
        for code, count, label in (
            ("CROSS_FARM_USAGE", cross_farm_usages, "alokacji FIFO"),
            ("CROSS_FARM_BATCH", cross_farm_batches, "partii gotowej paszy"),
        ):
            if count:
                result.issues.append(IntegrityIssue(
                    code=code,
                    object_label="feed",
                    object_id=None,
                    message=f"Wykryto {count} relacji między gospodarstwami w danych {label}.",
                    repairable=False,
                ))
