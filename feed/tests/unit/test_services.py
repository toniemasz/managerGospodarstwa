from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel
from feed.actions.productions import complete_production, mark_stage_1_done
from feed.selectors.inventory import inventory_dashboard
from feed.selectors.productions import (
    default_production_quantity,
    production_details_for_stages,
    validate_production_capacity,
)
from feed.selectors.recipes import recipe_costs


@pytest.fixture
def setup_data():
    """Przygotowuje podstawowe dane w bazie: składniki, dostawy i recepturę."""
    user = User.objects.create_user(username="feed-unit-owner")
    farm = get_or_create_user_farm(user)
    ing_bin = IngredientModel.objects.create(farm=farm, name="Kukurydza", is_in_bin=True)
    ing_bag = IngredientModel.objects.create(farm=farm, name="Koncentrat", is_in_bin=False)

    # Dostawy: 1000kg Kukurydzy, 500kg Koncentratu
    bin_delivery = DeliveryModel.objects.create(ingredient=ing_bin, date=timezone.now().date(), quantity_kg=1000, price_per_kg=1.0)
    bag_delivery = DeliveryModel.objects.create(ingredient=ing_bag, date=timezone.now().date(), quantity_kg=500, price_per_kg=3.0)
    from feed.actions.inventory import InventoryActions
    InventoryActions(farm).sync_delivery(bin_delivery)
    InventoryActions(farm).sync_delivery(bag_delivery)

    # Receptura: 80% Kukurydza, 20% Koncentrat
    recipe = RecipeModel.objects.create(farm=farm, name="Standardowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing_bin, percentage=80.00)
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing_bag, percentage=20.00)

    return {'farm': recipe.farm, 'ing_bin': ing_bin, 'ing_bag': ing_bag, 'recipe': recipe}


@pytest.mark.django_db
class TestFeedActionsAndSelectors:

    def test_inventory_dashboard_calculation(self, setup_data):
        dashboard = inventory_dashboard(setup_data['farm'])['inventory']

        bin_stock = next(i for i in dashboard if i.ingredient_id == setup_data['ing_bin'].id).current_stock
        bag_stock = next(i for i in dashboard if i.ingredient_id == setup_data['ing_bag'].id).current_stock

        assert bin_stock == Decimal('1000.00')
        assert bag_stock == Decimal('500.00')

    def test_validate_production_capacity_success(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.QUEUED
        )

        is_possible, errors = validate_production_capacity(setup_data['farm'], production.id)
        assert is_possible is True
        assert len(errors) == 0

    def test_validate_production_capacity_failure(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=3000,
            status=ProductionModel.Statuses.QUEUED
        )

        is_possible, errors = validate_production_capacity(setup_data['farm'], production.id)
        assert is_possible is False
        assert len(errors) > 0
        assert "Brakuje" in errors[0]

    def test_process_production_stage_1(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.QUEUED
        )

        success, msg = mark_stage_1_done(setup_data['farm'], production.id)
        assert success is True

        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.STAGE_1_DONE

    def test_complete_production_standard_flow(self, setup_data):
        # Tworzymy produkcję już po Etapie 1
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.STAGE_1_DONE
        )

        success, msg = complete_production(setup_data['farm'], production.id)
        assert success is True

        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.COMPLETED
        assert production.completed_at is not None

        # SPRAWDZAMY CZY MAGAZYN FAKTYCZNIE SPADŁ
        dashboard = inventory_dashboard(setup_data['farm'])['inventory']
        bin_stock = next(i for i in dashboard if i.ingredient_id == setup_data['ing_bin'].id).current_stock
        # 1000 - 800 = 200
        assert bin_stock == Decimal('200.00')

    def test_complete_production_skip_stages(self, setup_data):
        # Tworzymy produkcję prosto w kolejce
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=500,
            status=ProductionModel.Statuses.QUEUED
        )

        # Wymuszamy zakończenie z pominięciem etapów (checkbox "Od razu zatwierdź")
        success, msg = complete_production(setup_data['farm'], production.id, skip_stages=True)
        assert success is True

        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.COMPLETED

    def test_complete_production_blocks_if_no_stock(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=5000,  # Za dużo
            status=ProductionModel.Statuses.STAGE_1_DONE
        )

        success, msg = complete_production(setup_data['farm'], production.id)
        assert success is False
        assert "Brak wystarczającej ilości" in msg

        # Upewniamy się, że status się NIE zmienił
        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.STAGE_1_DONE

    def test_get_production_details_for_stages_splits_bin_and_bag_items(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.QUEUED
        )

        details = production_details_for_stages(setup_data['farm'], production.id)

        assert details['production'] == production
        assert details['stage1_items'][0]['name'] == "Kukurydza"
        assert details['stage1_items'][0]['weight_kg'] == Decimal('800.00')
        assert details['stage2_items'][0]['name'] == "Koncentrat"
        assert details['stage2_items'][0]['weight_kg'] == Decimal('200.00')

    def test_process_stage_1_rejects_non_queued_production(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.STAGE_1_DONE
        )

        success, message = mark_stage_1_done(setup_data['farm'], production.id)

        assert success is False
        assert "kolejce początkowej" in message

    def test_complete_production_rejects_before_stage_1(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=100,
            status=ProductionModel.Statuses.QUEUED
        )

        success, message = complete_production(setup_data['farm'], production.id)

        assert success is False
        assert "przed wykonaniem Etapu 1" in message

    def test_complete_production_rejects_already_completed(self, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=100,
            status=ProductionModel.Statuses.COMPLETED
        )

        success, message = complete_production(setup_data['farm'], production.id, skip_stages=True)

        assert success is False
        assert "wcześniej zaksięgowane" in message

    def test_get_calculator_data_returns_recipe_costs(self, setup_data):
        from feed.models import IngredientPriceConfigModel

        IngredientPriceConfigModel.objects.create(
            ingredient=setup_data['ing_bin'],
            price_per_kg=Decimal('1.00')
        )
        IngredientPriceConfigModel.objects.create(
            ingredient=setup_data['ing_bag'],
            price_per_kg=Decimal('3.00')
        )

        costs = recipe_costs(setup_data['farm'])

        assert len(costs) == 1
        assert costs[0].recipe_name == "Standardowa"
        assert costs[0].cost_per_kg == Decimal('1.40')

    def test_inventory_uses_low_stock_threshold_from_each_ingredient(self):
        user = User.objects.create_user(username='feed-settings-user')
        farm = get_or_create_user_farm(user)
        settings = get_farm_settings(farm)
        settings.default_production_quantity_kg = Decimal('1800.00')
        settings.save()

        low_threshold_ingredient = IngredientModel.objects.create(
            name="Pszenica",
            farm=farm,
            low_stock_threshold_kg=Decimal('750.00'),
        )
        enough_stock_ingredient = IngredientModel.objects.create(
            name="Jęczmień",
            farm=farm,
            low_stock_threshold_kg=Decimal('300.00'),
        )
        low_delivery = DeliveryModel.objects.create(
            ingredient=low_threshold_ingredient,
            date=timezone.now().date(),
            quantity_kg=Decimal('600.00'),
            price_per_kg=Decimal('1.00'),
        )
        enough_delivery = DeliveryModel.objects.create(
            ingredient=enough_stock_ingredient,
            date=timezone.now().date(),
            quantity_kg=Decimal('600.00'),
            price_per_kg=Decimal('1.00'),
        )
        from feed.actions.inventory import InventoryActions
        InventoryActions(farm).sync_delivery(low_delivery)
        InventoryActions(farm).sync_delivery(enough_delivery)

        dashboard = inventory_dashboard(farm)

        alert_ids = [item.ingredient_id for item in dashboard['low_stock_alerts']]
        assert alert_ids == [low_threshold_ingredient.id]
        assert dashboard['low_stock_alerts'][0].low_stock_threshold_kg == Decimal('750.00')
        assert default_production_quantity(farm) == Decimal('1800.00')
