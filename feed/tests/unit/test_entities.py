import pytest
from decimal import Decimal
from feed.services.feed_calculators import ProductionCalculator, RecipeCostCalculator


class TestProductionCalculator:

    @pytest.fixture
    def base_items(self):
        return [
            {'ingredient_id': 1, 'name': 'Pszenica', 'is_in_bin': True, 'percentage': Decimal('60.00')},
            {'ingredient_id': 2, 'name': 'Soja', 'is_in_bin': False, 'percentage': Decimal('40.00')},
        ]

    def test_valid_base_proportions(self, base_items):
        # Proporcje 60 + 40 = 100
        calc = ProductionCalculator(quantity_kg=1000, base_recipe_items=base_items)
        assert calc.is_valid_proportions() is True

    def test_invalid_base_proportions(self, base_items):
        # Zmieniamy bazę tak, by dawała 90%
        base_items[0]['percentage'] = Decimal('50.00')
        calc = ProductionCalculator(quantity_kg=1000, base_recipe_items=base_items)
        assert calc.is_valid_proportions() is False

    def test_valid_custom_proportions(self, base_items):
        # Baza ma 100%, ale nadpisujemy ją na 70 + 30
        custom_data = {'1': '70.00', '2': '30.00'}
        calc = ProductionCalculator(quantity_kg=1000, base_recipe_items=base_items, custom_recipe_data=custom_data)
        assert calc.is_valid_proportions() is True

    def test_invalid_custom_proportions(self, base_items):
        # Nadpisujemy na błędne proporcje (70 + 20 = 90)
        custom_data = {'1': '70.00', '2': '20.00'}
        calc = ProductionCalculator(quantity_kg=1000, base_recipe_items=base_items, custom_recipe_data=custom_data)
        assert calc.is_valid_proportions() is False

    def test_calculate_requirements_base_recipe(self, base_items):
        # Produkcja 2000 kg z bazy (60% i 40%)
        calc = ProductionCalculator(quantity_kg=2000, base_recipe_items=base_items)
        reqs = calc.get_requirements()

        assert len(reqs) == 2

        pszenica_req = next(r for r in reqs if r.ingredient_id == 1)
        assert pszenica_req.required_kg == Decimal('1200.00')  # 60% z 2000
        assert pszenica_req.is_in_bin is True

        soja_req = next(r for r in reqs if r.ingredient_id == 2)
        assert soja_req.required_kg == Decimal('800.00')  # 40% z 2000
        assert soja_req.is_in_bin is False

    def test_calculate_requirements_with_custom_recipe(self, base_items):
        # Produkcja 1000 kg, ale zmieniamy proporcje (50% i 50%)
        custom_data = {'1': '50.00', '2': '50.00'}
        calc = ProductionCalculator(quantity_kg=1000, base_recipe_items=base_items, custom_recipe_data=custom_data)
        reqs = calc.get_requirements()

        pszenica_req = next(r for r in reqs if r.ingredient_id == 1)
        assert pszenica_req.required_kg == Decimal('500.00')  # 50% z 1000

        soja_req = next(r for r in reqs if r.ingredient_id == 2)
        assert soja_req.required_kg == Decimal('500.00')  # 50% z 1000


class TestRecipeCostCalculator:


    def test_calculate_cost_correctly(self):

        recipe_items = [
            {'ingredient_id': 1, 'percentage': Decimal('60.00')},  # np. Pszenica
            {'ingredient_id': 2, 'percentage': Decimal('40.00')},  # np. Soja
        ]

        price_map = {
            1: Decimal('1.00'),  # Pszenica po 1 zł
            2: Decimal('3.00')  # Soja po 3 zł
        }

        calc = RecipeCostCalculator(
            recipe_name="Pasza Premium",
            recipe_items=recipe_items,
            price_map=price_map
        )

        result = calc.calculate_cost()

        # Oczekujemy: (0.6 * 1.00) + (0.4 * 3.00) = 0.60 + 1.20 = 1.80
        assert result.recipe_name == "Pasza Premium"
        assert result.cost_per_kg == Decimal('1.80')

    def test_calculate_cost_with_missing_price(self):
        recipe_items = [
            {'ingredient_id': 1, 'ingredient_name': 'Pszenica', 'percentage': Decimal('100.00')}
        ]
        price_map = {}

        calc = RecipeCostCalculator("Pasza bez ceny", recipe_items, price_map)
        result = calc.calculate_cost()

        assert result.is_complete is False
        assert result.missing_price_ingredients == ['Pszenica']
        assert result.item_costs[0]['cost_per_kg'] is None
