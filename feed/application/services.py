from decimal import Decimal
from django.utils import timezone
from django.db import transaction

from feed.infrastructure.repositories import FeedRepository
from feed.domain.entities import ProductionCalculator, IngredientRequirement, InventoryItem, RecipeCostCalculator


class FeedManagementService:
    def __init__(self, repository: FeedRepository = None):
        self.repository = repository or FeedRepository()

    def get_inventory_dashboard(self) -> dict:
        """Orkiestruje wyliczanie stanu magazynu bez dotykania ORM."""
        # 1. Pobranie danych przez repozytorium
        ingredients = self.repository.get_all_ingredients()
        delivery_map = self.repository.get_delivery_aggregates()
        completed_productions = self.repository.get_completed_productions()

        consumed_map = {ing.id: Decimal('0.00') for ing in ingredients}

        # 2. Orkiestracja reguł biznesowych z Domeny
        for prod in completed_productions:
            base_items = [
                {
                    'ingredient_id': item.ingredient.id,
                    'name': item.ingredient.name,
                    'is_in_bin': item.ingredient.is_in_bin,
                    'percentage': item.percentage
                }
                for item in prod.recipe.items.all()
            ]

            calculator = ProductionCalculator(
                quantity_kg=prod.quantity_kg,
                base_recipe_items=base_items,
                custom_recipe_data=prod.custom_recipe_data
            )

            for req in calculator.get_requirements():
                if req.ingredient_id in consumed_map:
                    consumed_map[req.ingredient_id] += req.required_kg

        # 3. Złożenie wyników
        inventory_state = []
        for ing in ingredients:
            total_delivered = delivery_map.get(ing.id, Decimal('0.00'))
            total_consumed = consumed_map.get(ing.id, Decimal('0.00'))

            inventory_state.append(InventoryItem(
                ingredient_id=ing.id,
                name=ing.name,
                is_in_bin=ing.is_in_bin,
                total_delivered=total_delivered,
                total_used=total_consumed
            ))

        low_stock = [item for item in inventory_state if item.current_stock < 500]
        total_inventory_kg = sum((item.current_stock for item in inventory_state), Decimal('0.00'))

        return {
            'inventory': inventory_state,
            'low_stock_alerts': low_stock,
            'total_inventory_kg': total_inventory_kg
        }

    def validate_production_capacity(self, production_id: int) -> tuple[bool, list[str]]:
        production = self.repository.get_production_for_processing(production_id)
        inventory_state = self.get_inventory_dashboard()['inventory']
        inventory_map = {item.ingredient_id: item.current_stock for item in inventory_state}
        name_map = {item.ingredient_id: item.name for item in inventory_state}

        base_items = [
            {
                'ingredient_id': item.ingredient.id,
                'name': item.ingredient.name,
                'is_in_bin': item.ingredient.is_in_bin,
                'percentage': item.percentage
            }
            for item in production.recipe.items.all()
        ]

        calculator = ProductionCalculator(
            quantity_kg=production.quantity_kg,
            base_recipe_items=base_items,
            custom_recipe_data=production.custom_recipe_data
        )

        errors = []
        for req in calculator.get_requirements():
            available = inventory_map.get(req.ingredient_id, Decimal('0.00'))
            if req.required_kg > available:
                ing_name = name_map.get(req.ingredient_id, req.name)
                errors.append(
                    f"Brakuje {req.required_kg - available:.2f} kg składnika '{ing_name}' (Dostępne: {available:.2f} kg)")

        return len(errors) == 0, errors

    def get_production_details_for_stages(self, production_id: int) -> dict:
        production = self.repository.get_production_for_processing(production_id)

        base_items = [
            {
                'ingredient_id': item.ingredient.id,
                'name': item.ingredient.name,
                'is_in_bin': item.ingredient.is_in_bin,
                'percentage': item.percentage
            }
            for item in production.recipe.items.all()
        ]

        calculator = ProductionCalculator(
            quantity_kg=production.quantity_kg,
            base_recipe_items=base_items,
            custom_recipe_data=production.custom_recipe_data
        )

        sorted_reqs = sorted(calculator.get_requirements(), key=lambda x: x.name)

        stage1_items = [{'id': r.ingredient_id, 'name': r.name, 'is_in_bin': r.is_in_bin, 'percentage': r.percentage,
                         'weight_kg': r.required_kg} for r in sorted_reqs if r.is_in_bin]
        stage2_items = [{'id': r.ingredient_id, 'name': r.name, 'is_in_bin': r.is_in_bin, 'percentage': r.percentage,
                         'weight_kg': r.required_kg} for r in sorted_reqs if not r.is_in_bin]

        return {
            'production': production,
            'stage1_items': stage1_items,
            'stage2_items': stage2_items
        }

    @transaction.atomic
    def process_production_stage_1(self, production_id: int) -> tuple[bool, str]:
        production = self.repository.get_production_for_processing(production_id, lock_for_update=True)
        # UWAGA: Tutaj pojawia się tzw. zjawisko magic stringów. Statusy też powinny być wydzielone,
        # ale na potrzeby frameworka akceptujemy 'QUEUED' i 'STAGE_1_DONE'.
        if production.status != 'QUEUED':
            return False, "Śrutowanie nie znajduje się w kolejce początkowej."

        production.status = 'STAGE_1_DONE'
        self.repository.save_production(production)
        return True, "Zakończono pobieranie z binów. Gotowe do Etapu 2."

    @transaction.atomic
    def complete_production(self, production_id: int, skip_stages: bool = False, force_inventory: bool = False) -> \
    tuple[bool, str]:
        production = self.repository.get_production_for_processing(production_id, lock_for_update=True)

        if not skip_stages and production.status != 'STAGE_1_DONE':
            return False, "Nie można zakończyć produkcji przed wykonaniem Etapu 1."

        if production.status == 'COMPLETED':
            return False, "To śrutowanie zostało już wcześniej zaksięgowane."

        if not force_inventory:
            is_possible, errors = self.validate_production_capacity(production_id)
            if not is_possible:
                return False, "Brak wystarczającej ilości składników na magazynie: " + " | ".join(errors)

        production.status = 'COMPLETED'
        production.completed_at = timezone.now()
        self.repository.save_production(production)
        return True, "Śrutowanie zakończone pomyślnie. Zaktualizowano stany magazynowe."

    def get_calculator_data(self):
        """
        Orkiestruje wyliczanie kosztów.
        Pobiera dane z repozytorium, formuje słowniki i deleguje matematykę do Domeny.
        """
        # 1. Pobieramy surowe dane z bazy (przez Repozytorium)
        recipes = self.repository.get_recipes_with_items()
        prices_map = self.repository.get_ingredient_prices_map()

        costs = []

        # 2. Orkiestracja i delegacja do Domeny
        for recipe in recipes:
            # Budujemy czysty słownik, by uwolnić Domenę od ORM Django
            base_items = [
                {
                    'ingredient_id': item.ingredient_id,
                    'percentage': item.percentage
                }
                for item in recipe.items.all()
            ]

            # Tworzymy kalkulator domenowy
            calculator = RecipeCostCalculator(
                recipe_name=recipe.name,
                recipe_items=base_items,
                price_map=prices_map
            )

            # Pobieramy gotowy wynik
            costs.append(calculator.calculate_cost())

        return costs