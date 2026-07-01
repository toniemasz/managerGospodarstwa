from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from farms.services.audit_log_service import log_action
from feed.models import ProductionModel, RecipeItemModel, RecipeModel, RecipeVersionItemModel, RecipeVersionModel
from feed.services.inventory_service import InventoryMovementService


PERCENT_TOTAL = Decimal('100.00')
PERCENT_TOLERANCE = Decimal('0.01')


@dataclass(frozen=True)
class RecipeVersionUpdateResult:
    production_count: int
    completed_count: int
    custom_recipe_count: int
    rebuild_result: dict[str, int] | None = None


def _percentage_signature(items) -> tuple[tuple[int, Decimal], ...]:
    return tuple(sorted(
        (item.ingredient_id, Decimal(item.percentage).quantize(Decimal('0.01')))
        for item in items
    ))


class RecipeVersionService:
    def __init__(self, *, farm=None, user=None):
        self.farm = farm
        self.user = user

    @transaction.atomic
    def ensure_current_version(
        self,
        recipe: RecipeModel,
        *,
        change_note: str = '',
    ) -> tuple[RecipeVersionModel, bool]:
        recipe = RecipeModel.objects.select_for_update().get(pk=recipe.pk)
        if self.farm is not None and recipe.farm_id != self.farm.id:
            raise ValidationError("Receptura nie należy do tego gospodarstwa.")

        recipe_items = list(
            RecipeItemModel.objects
            .filter(recipe=recipe)
            .select_related('ingredient')
            .order_by('ingredient_id')
        )
        self._validate_recipe_items(recipe_items)

        current_version = (
            RecipeVersionModel.objects
            .select_for_update()
            .filter(recipe=recipe, is_current=True)
            .prefetch_related('items')
            .order_by('-version_number', '-id')
            .first()
        )

        new_signature = _percentage_signature(recipe_items)
        if current_version is not None:
            current_items = list(current_version.items.all())
            if _percentage_signature(current_items) == new_signature:
                return current_version, False

        now = timezone.now()
        if current_version is not None:
            current_version.is_current = False
            current_version.valid_to = now
            current_version.save(update_fields=['is_current', 'valid_to'])

        next_number = (
            RecipeVersionModel.objects
            .filter(recipe=recipe)
            .aggregate(max_number=Max('version_number'))['max_number']
            or 0
        ) + 1
        version = RecipeVersionModel.objects.create(
            recipe=recipe,
            version_number=next_number,
            created_by=self.user if getattr(self.user, 'is_authenticated', False) else None,
            valid_from=now,
            change_note=change_note,
            is_current=True,
        )
        RecipeVersionItemModel.objects.bulk_create([
            RecipeVersionItemModel(
                recipe_version=version,
                ingredient=item.ingredient,
                percentage=item.percentage,
            )
            for item in recipe_items
        ])
        log_action(
            farm=recipe.farm,
            user=self.user,
            action='RECIPE_VERSION_CREATED',
            obj=version,
            metadata={
                'recipe_id': str(recipe.pk),
                'recipe_version_id': str(version.pk),
                'version_number': version.version_number,
                'item_count': len(recipe_items),
                'change_note': change_note,
            },
        )
        return version, True

    @transaction.atomic
    def create_new_version(
        self,
        *,
        recipe: RecipeModel,
        items: list[dict],
        source_version: RecipeVersionModel | None = None,
        change_note: str = '',
    ) -> RecipeVersionModel:
        recipe = RecipeModel.objects.select_for_update().get(pk=recipe.pk)
        if self.farm is not None and recipe.farm_id != self.farm.id:
            raise ValidationError("Receptura nie należy do tego gospodarstwa.")
        if source_version is not None and source_version.recipe_id != recipe.pk:
            raise ValidationError("Wersja źródłowa nie należy do tej receptury.")

        self._validate_item_payload(items)
        now = timezone.now()
        current_version = (
            RecipeVersionModel.objects
            .select_for_update()
            .filter(recipe=recipe, is_current=True)
            .first()
        )
        if current_version is not None:
            current_version.is_current = False
            current_version.valid_to = now
            current_version.save(update_fields=['is_current', 'valid_to'])

        next_number = (
            RecipeVersionModel.objects
            .filter(recipe=recipe)
            .aggregate(max_number=Max('version_number'))['max_number']
            or 0
        ) + 1
        version = RecipeVersionModel.objects.create(
            recipe=recipe,
            version_number=next_number,
            created_by=self.user if getattr(self.user, 'is_authenticated', False) else None,
            valid_from=now,
            change_note=change_note,
            is_current=True,
        )
        self._replace_version_items(version, items)
        self._sync_recipe_items_to_version(version)
        log_action(
            farm=recipe.farm,
            user=self.user,
            action='RECIPE_VERSION_CREATED',
            obj=version,
            metadata={
                'recipe_id': str(recipe.pk),
                'recipe_version_id': str(version.pk),
                'version_number': version.version_number,
                'source_version_id': str(source_version.pk) if source_version else '',
                'item_count': len(items),
                'change_note': change_note,
            },
        )
        return version

    @transaction.atomic
    def update_existing_version(
        self,
        *,
        version: RecipeVersionModel,
        items: list[dict],
        confirm_recalculate: bool = False,
    ) -> RecipeVersionUpdateResult:
        version = (
            RecipeVersionModel.objects
            .select_for_update()
            .select_related('recipe')
            .get(pk=version.pk)
        )
        if self.farm is not None and version.recipe.farm_id != self.farm.id:
            raise ValidationError("Wersja receptury nie należy do tego gospodarstwa.")

        production_count = ProductionModel.objects.filter(recipe_version=version, recipe__farm=version.recipe.farm).count()
        if production_count and not confirm_recalculate:
            raise ValidationError(
                "Ta wersja ma przypisane śrutowania. Potwierdź, że zapis przeliczy produkcje tej wersji."
            )

        self._validate_item_payload(items)
        self._replace_version_items(version, items)
        if version.is_current:
            self._sync_recipe_items_to_version(version)

        completed = list(
            ProductionModel.objects
            .select_for_update()
            .filter(
                recipe_version=version,
                recipe__farm=version.recipe.farm,
                status=ProductionModel.Statuses.COMPLETED,
            )
            .order_by('date', 'time', 'id')
        )
        completed_ids = [production.pk for production in completed]
        custom_recipe_count = sum(1 for production in completed if production.custom_recipe_data)
        rebuild_result = None
        if completed_ids:
            rebuild_result = InventoryMovementService(version.recipe.farm).rebuild(
                prefer_existing_movements=True,
                reconstruct_production_ids=set(completed_ids),
            )

        metadata = {
            'recipe_id': str(version.recipe_id),
            'recipe_version_id': str(version.pk),
            'version_number': version.version_number,
            'production_ids': [str(pk) for pk in completed_ids],
            'production_count': production_count,
            'completed_count': len(completed_ids),
            'custom_recipe_count': custom_recipe_count,
            'rebuild_result': rebuild_result or {},
        }
        log_action(
            farm=version.recipe.farm,
            user=self.user,
            action='RECIPE_VERSION_UPDATED',
            obj=version,
            metadata=metadata,
        )
        if completed_ids:
            log_action(
                farm=version.recipe.farm,
                user=self.user,
                action='RECIPE_VERSION_PRODUCTIONS_RECALCULATED',
                obj=version,
                metadata=metadata,
            )
        return RecipeVersionUpdateResult(
            production_count=production_count,
            completed_count=len(completed_ids),
            custom_recipe_count=custom_recipe_count,
            rebuild_result=rebuild_result,
        )

    @staticmethod
    def _validate_recipe_items(items) -> None:
        if not items:
            return
        total = sum((Decimal(item.percentage) for item in items), Decimal('0.00'))
        if abs(total - PERCENT_TOTAL) > PERCENT_TOLERANCE:
            raise ValidationError(
                f"Suma procentowych udziałów składników musi wynosić 100%. Obecnie wynosi: {total}%."
            )

    @classmethod
    def _validate_item_payload(cls, items: list[dict]) -> None:
        if not items:
            raise ValidationError("Wersja receptury musi mieć co najmniej jeden składnik.")
        ingredient_ids = set()
        total = Decimal('0.00')
        for item in items:
            ingredient = item['ingredient']
            percentage = Decimal(item['percentage'])
            if ingredient.pk in ingredient_ids:
                raise ValidationError(f"Składnik {ingredient.name} został dodany do wersji więcej niż raz.")
            ingredient_ids.add(ingredient.pk)
            total += percentage
        if abs(total - PERCENT_TOTAL) > PERCENT_TOLERANCE:
            raise ValidationError(
                f"Suma procentowych udziałów składników musi wynosić 100%. Obecnie wynosi: {total}%."
            )

    @staticmethod
    def _replace_version_items(version: RecipeVersionModel, items: list[dict]) -> None:
        RecipeVersionItemModel.objects.filter(recipe_version=version).delete()
        RecipeVersionItemModel.objects.bulk_create([
            RecipeVersionItemModel(
                recipe_version=version,
                ingredient=item['ingredient'],
                percentage=item['percentage'],
            )
            for item in items
        ])

    @staticmethod
    def _sync_recipe_items_to_version(version: RecipeVersionModel) -> None:
        RecipeItemModel.objects.filter(recipe=version.recipe).delete()
        RecipeItemModel.objects.bulk_create([
            RecipeItemModel(
                recipe=version.recipe,
                ingredient=item.ingredient,
                percentage=item.percentage,
            )
            for item in version.items.select_related('ingredient').order_by('ingredient__name', 'id')
        ])
