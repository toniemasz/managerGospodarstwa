from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db.models.deletion import RestrictedError

from costs.models import CostModel
from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from feed.actions.inventory import InventoryActions
from feed.actions.productions import complete_production
from feed.models import (
    DeliveryModel,
    FinishedFeedBatchModel,
    IngredientModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)
from feed.services.integrity import FeedIntegrityService
from feed.services.production_reversal import ProductionSettlementReversalWorkflow


def _completed_production():
    user = User.objects.create_user(username="integrity-owner")
    farm = get_or_create_user_farm(user)
    ingredient = IngredientModel.objects.create(farm=farm, name="Pszenica integralności")
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2026, 1, 1),
        quantity_kg=Decimal("500.00"),
        price_per_kg=Decimal("1.25000"),
    )
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(farm=farm, name="Pasza integralności")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal("100.00"))
    production = ProductionModel.objects.create(
        recipe=recipe,
        date=date(2026, 1, 2),
        quantity_kg=Decimal("100.00"),
        status=ProductionModel.Statuses.STAGE_1_DONE,
    )
    success, message = complete_production(farm, production.pk, user=user, create_serving=True)
    assert success, message
    production.refresh_from_db()
    delivery.refresh_from_db()
    return user, farm, delivery, production


@pytest.mark.django_db
def test_integrity_audit_is_read_only_by_default_and_repairs_only_with_apply():
    _user, farm, _delivery, production = _completed_production()
    CostModel.objects.filter(production=production).update(amount=Decimal("1.00"))
    FinishedFeedBatchModel.objects.filter(production=production).update(total_cost=Decimal("2.00"))

    preview = FeedIntegrityService(farm).audit()

    assert any(issue.code == "PRODUCTION_COST_MISMATCH" for issue in preview.issues)
    assert CostModel.objects.get(production=production).amount == Decimal("1.00")

    applied = FeedIntegrityService(farm).audit(apply=True)

    production.refresh_from_db()
    assert applied.repaired >= 1
    assert CostModel.objects.get(production=production).amount == production.feed_cost_total
    assert FinishedFeedBatchModel.objects.get(production=production).total_cost == production.feed_cost_total


@pytest.mark.django_db
def test_reversal_withdraws_all_production_settlement_artifacts_and_is_audited():
    user, farm, delivery, production = _completed_production()

    result = ProductionSettlementReversalWorkflow(farm=farm, user=user).reverse(
        production.pk,
        reason="Korekta ilości",
    )

    production.refresh_from_db()
    delivery.refresh_from_db()
    assert result.new_status == ProductionModel.Statuses.STAGE_1_DONE
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE
    assert production.completed_at is None
    assert delivery.remaining_quantity_kg == delivery.quantity_kg
    assert not production.ingredient_usages.exists()
    assert not CostModel.objects.filter(production=production).exists()
    assert not FinishedFeedBatchModel.objects.filter(production=production).exists()
    assert AuditLogModel.objects.filter(
        farm=farm,
        action="PRODUCTION_SETTLEMENT_REVERSED",
        metadata__reason="Korekta ilości",
    ).exists()


@pytest.mark.django_db
def test_database_relation_blocks_queryset_delete_that_bypasses_domain_action():
    _user, _farm, _delivery, production = _completed_production()

    with pytest.raises(RestrictedError):
        ProductionModel.objects.filter(pk=production.pk).delete()
