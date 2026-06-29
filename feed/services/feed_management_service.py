from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum

from farms.services.settings_service import get_farm_settings
from feed.domain.rules import DEFAULT_PRODUCTION_QUANTITY_KG, LOW_STOCK_THRESHOLD_KG
from feed.services.feed_calculators import InventoryItem, ProductionCalculator, RecipeCostCalculator
from feed.services.feed_repository import FeedRepository
from feed.models import ProductionModel
from feed.services.inventory_service import InventoryMovementService


class FeedManagementService:
    def __init__(self, farm=None, repository: FeedRepository = None):
        self.farm = farm
        self.repository = repository or FeedRepository(farm=farm)
        self.settings = get_farm_settings(farm) if farm is not None else None

    @staticmethod
    def _recipe_items_from_production(production) -> list[dict]:
        return [
            {
                'ingredient_id': item.ingredient.id,
                'name': item.ingredient.name,
                'is_in_bin': item.ingredient.is_in_bin,
                'percentage': item.percentage,
            }
            for item in production.recipe.items.all()
        ]

    def _calculator_for_production(self, production) -> ProductionCalculator:
        return ProductionCalculator(
            quantity_kg=production.quantity_kg,
            base_recipe_items=self._recipe_items_from_production(production),
            custom_recipe_data=production.custom_recipe_data,
        )

    def get_inventory_dashboard(self) -> dict:
        """Orkiestruje wyliczanie stanu magazynu bez dotykania ORM."""
        ingredients = self.repository.get_all_ingredients()
        movement_totals = InventoryMovementService(self.farm).movement_totals()

        inventory_state = []
        for ing in ingredients:
            total_delivered, total_consumed = movement_totals.get(
                ing.id,
                (Decimal('0.00'), Decimal('0.00')),
            )

            inventory_state.append(InventoryItem(
                ingredient_id=ing.id,
                name=ing.name,
                is_in_bin=ing.is_in_bin,
                low_stock_threshold_kg=ing.low_stock_threshold_kg,
                total_delivered=total_delivered,
                total_used=total_consumed,
            ))

        low_stock = [item for item in inventory_state if item.is_low_stock]
        total_inventory_kg = sum((item.current_stock for item in inventory_state), Decimal('0.00'))

        return {
            'inventory': inventory_state,
            'low_stock_alerts': low_stock,
            'total_inventory_kg': total_inventory_kg,
            'total_inventory_t': total_inventory_kg / Decimal('1000.00'),
        }

    def get_low_stock_threshold(self) -> Decimal:
        return LOW_STOCK_THRESHOLD_KG

    def get_default_production_quantity(self) -> Decimal:
        return self.settings.default_production_quantity_kg if self.settings else DEFAULT_PRODUCTION_QUANTITY_KG

    def validate_production_capacity(self, production_id: int) -> tuple[bool, list[str]]:
        production = self.repository.get_production_for_processing(production_id)
        inventory_state = self.get_inventory_dashboard()['inventory']
        inventory_map = {item.ingredient_id: item.current_stock for item in inventory_state}
        name_map = {item.ingredient_id: item.name for item in inventory_state}

        errors = []
        for req in self._calculator_for_production(production).get_requirements():
            available = inventory_map.get(req.ingredient_id, Decimal('0.00'))
            if req.required_kg > available:
                ing_name = name_map.get(req.ingredient_id, req.name)
                errors.append(
                    f"Brakuje {req.required_kg - available:.2f} kg składnika '{ing_name}' (Dostępne: {available:.2f} kg)")

        return len(errors) == 0, errors

    def get_production_details_for_stages(self, production_id: int) -> dict:
        production = self.repository.get_production_for_processing(production_id)
        price_map = self.repository.get_latest_delivery_prices_map()

        sorted_reqs = sorted(self._calculator_for_production(production).get_requirements(), key=lambda x: x.name)

        enriched_reqs = []
        total_cost = Decimal('0.00')
        for req in sorted_reqs:
            price = price_map.get(req.ingredient_id, Decimal('0.00'))
            cost = req.required_kg * price
            total_cost += cost
            enriched_reqs.append({
                'id': req.ingredient_id,
                'name': req.name,
                'is_in_bin': req.is_in_bin,
                'percentage': req.percentage,
                'weight_kg': req.required_kg,
                'price_per_kg': price,
                'cost': cost,
            })

        stage1_items = [item for item in enriched_reqs if item['is_in_bin']]
        stage2_items = [item for item in enriched_reqs if not item['is_in_bin']]
        cost_per_kg = (total_cost / production.quantity_kg) if production.quantity_kg else Decimal('0.00')

        return {
            'production': production,
            'stage1_items': stage1_items,
            'stage2_items': stage2_items,
            'all_items': enriched_reqs,
            'production_cost': {
                'total_cost': total_cost,
                'cost_per_kg': cost_per_kg,
                'cost_per_ton': cost_per_kg * Decimal('1000.00'),
            },
        }

    @transaction.atomic
    def process_production_stage_1(self, production_id: int) -> tuple[bool, str]:
        production = self.repository.get_production_for_processing(production_id, lock_for_update=True)
        if production.status != 'QUEUED':
            return False, "Śrutowanie nie znajduje się w kolejce początkowej."

        production.status = 'STAGE_1_DONE'
        self.repository.save_production(production)
        return True, "Zakończono pobieranie z binów. Gotowe do Etapu 2."

    def complete_production(self, production_id: int, skip_stages: bool = False, force_inventory: bool = False, user=None) -> \
    tuple[bool, str]:
        try:
            with transaction.atomic():
                production = self.repository.get_production_for_processing(production_id, lock_for_update=True)

                if production.status == 'COMPLETED':
                    return False, "To śrutowanie zostało już wcześniej zaksięgowane."

                if not skip_stages and production.status != 'STAGE_1_DONE':
                    return False, "Nie można zakończyć produkcji przed wykonaniem Etapu 1."

                if not force_inventory:
                    is_possible, errors = self.validate_production_capacity(production_id)
                    if not is_possible:
                        return False, "Brak wystarczającej ilości składników na magazynie: " + " | ".join(errors)

                production.status = 'COMPLETED'
                production.completed_at = timezone.now()
                production._skip_inventory_sync = True
                self.repository.save_production(production)
                InventoryMovementService(self.farm).book_production(
                    production,
                    user=user,
                    forced=force_inventory,
                )
        except ValidationError as error:
            message = error.messages[0] if hasattr(error, "messages") else str(error)
            return False, message
        return True, "Śrutowanie zakończone pomyślnie. Zaktualizowano stany magazynowe i koszt FIFO."

    def get_calculator_data(self):
        """
        Orkiestruje wyliczanie kosztów.
        Pobiera dane z repozytorium, formuje słowniki i deleguje matematykę do Domeny.
        """
        return self.get_recipe_costs()

    def get_recipe_costs(self, price_overrides: dict[int, Decimal] | None = None):
        recipes = self.repository.get_recipes_with_items()
        prices_map = self.repository.get_latest_delivery_prices_map()
        if price_overrides:
            prices_map.update(price_overrides)

        costs = []

        for recipe in recipes:
            base_items = [
                {
                    'ingredient_id': item.ingredient_id,
                    'ingredient_name': item.ingredient.name,
                    'percentage': item.percentage
                }
                for item in recipe.items.all()
            ]

            calculator = RecipeCostCalculator(
                recipe_id=recipe.id,
                recipe_name=recipe.name,
                recipe_items=base_items,
                price_map=prices_map
            )

            costs.append(calculator.calculate_cost())

        return costs

    def get_calculator_price_rows(self, overrides: dict[int, Decimal] | None = None) -> list[dict]:
        prices_map = self.repository.get_latest_delivery_prices_map()
        sources = self.repository.get_latest_delivery_price_sources()
        if overrides:
            prices_map.update(overrides)

        rows = []
        for ingredient in self.repository.get_all_ingredients():
            delivery = sources.get(ingredient.id)
            price = prices_map.get(ingredient.id)
            rows.append({
                'ingredient': ingredient,
                'price_per_kg': price,
                'source_date': delivery.date if delivery else None,
                'has_delivery': delivery is not None,
                'has_price': price is not None,
            })
        return rows

    def get_recipe_detail(self, recipe_id: int, date_from=None, date_to=None, production_year: int | None = None) -> dict:
        recipe = self.repository.get_recipe_with_items(recipe_id)
        prices_map = self.repository.get_latest_delivery_prices_map()

        base_items = [
            {
                'ingredient_id': item.ingredient_id,
                'ingredient_name': item.ingredient.name,
                'percentage': item.percentage,
            }
            for item in recipe.items.all()
        ]
        cost = RecipeCostCalculator(
            recipe_id=recipe.id,
            recipe_name=recipe.name,
            recipe_items=base_items,
            price_map=prices_map,
        ).calculate_cost()

        all_productions = self.repository.get_productions_for_recipe(recipe_id)
        year = production_year or timezone.localdate().year
        available_years = [
            row.year for row in all_productions.filter(
                status=ProductionModel.Statuses.COMPLETED,
            ).dates('date', 'year', order='DESC')
        ]
        if year not in available_years:
            available_years.insert(0, year)
        yearly_quantity_kg = all_productions.filter(
            status=ProductionModel.Statuses.COMPLETED,
            date__year=year,
        ).aggregate(quantity_kg=Sum('quantity_kg'))['quantity_kg'] or Decimal('0.00')

        productions = all_productions
        if date_from is not None:
            productions = productions.filter(date__gte=date_from)
        if date_to is not None:
            productions = productions.filter(date__lte=date_to)
        aggregate = productions.aggregate(
            total_count=Count('id'),
            total_planned_kg=Sum('quantity_kg'),
        )

        completed = productions.filter(status=ProductionModel.Statuses.COMPLETED).aggregate(
            count=Count('id'),
            quantity_kg=Sum('quantity_kg'),
            feed_cost=Sum('feed_cost_total'),
        )
        queued = productions.filter(status=ProductionModel.Statuses.QUEUED).aggregate(
            count=Count('id'),
            quantity_kg=Sum('quantity_kg'),
        )
        in_progress = productions.filter(status=ProductionModel.Statuses.STAGE_1_DONE).aggregate(
            count=Count('id'),
            quantity_kg=Sum('quantity_kg'),
        )

        return {
            'recipe': recipe,
            'cost': cost,
            'productions': productions[:20],
            'stats': {
                'total_count': aggregate['total_count'] or 0,
                'total_planned_kg': aggregate['total_planned_kg'] or Decimal('0.00'),
                'completed_count': completed['count'] or 0,
                'completed_kg': completed['quantity_kg'] or Decimal('0.00'),
                'completed_t': (completed['quantity_kg'] or Decimal('0.00'))/ Decimal('1000.00'),
                'completed_cost': completed['feed_cost'] or Decimal('0.00'),
                'queued_count': queued['count'] or 0,
                'queued_kg': queued['quantity_kg'] or Decimal('0.00'),
                'in_progress_count': in_progress['count'] or 0,
                'in_progress_kg': in_progress['quantity_kg'] or Decimal('0.00'),
            },
            'yearly_production': {
                'year': year,
                'available_years': available_years,
                'quantity_kg': yearly_quantity_kg,
                'quantity_t': yearly_quantity_kg / Decimal('1000.00'),
            },
        }
