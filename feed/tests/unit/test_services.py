from decimal import Decimal
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel
from feed.services.feed_management_service import FeedManagementService


@pytest.fixture
def service():
    return FeedManagementService()


@pytest.fixture
def setup_data():
    """Przygotowuje podstawowe dane w bazie: składniki, dostawy i recepturę."""
    ing_bin = IngredientModel.objects.create(name="Kukurydza", is_in_bin=True)
    ing_bag = IngredientModel.objects.create(name="Koncentrat", is_in_bin=False)

    # Dostawy: 1000kg Kukurydzy, 500kg Koncentratu
    DeliveryModel.objects.create(ingredient=ing_bin, date=timezone.now().date(), quantity_kg=1000, price_per_kg=1.0)
    DeliveryModel.objects.create(ingredient=ing_bag, date=timezone.now().date(), quantity_kg=500, price_per_kg=3.0)

    # Receptura: 80% Kukurydza, 20% Koncentrat
    recipe = RecipeModel.objects.create(name="Standardowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing_bin, percentage=80.00)
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing_bag, percentage=20.00)

    return {'ing_bin': ing_bin, 'ing_bag': ing_bag, 'recipe': recipe}


@pytest.mark.django_db
class TestFeedManagementService:

    def test_inventory_dashboard_calculation(self, service, setup_data):
        # Na start magazyn powinien mieć to, co z dostawy
        dashboard = service.get_inventory_dashboard()['inventory']

        bin_stock = next(i for i in dashboard if i.ingredient_id == setup_data['ing_bin'].id).current_stock
        bag_stock = next(i for i in dashboard if i.ingredient_id == setup_data['ing_bag'].id).current_stock

        assert bin_stock == Decimal('1000.00')
        assert bag_stock == Decimal('500.00')

    def test_validate_production_capacity_success(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.QUEUED
        )

        is_possible, errors = service.validate_production_capacity(production.id)
        assert is_possible is True
        assert len(errors) == 0

    def test_validate_production_capacity_failure(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=3000,
            status=ProductionModel.Statuses.QUEUED
        )

        is_possible, errors = service.validate_production_capacity(production.id)
        assert is_possible is False
        assert len(errors) > 0
        assert "Brakuje" in errors[0]

    def test_process_production_stage_1(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.QUEUED
        )

        success, msg = service.process_production_stage_1(production.id)
        assert success is True

        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.STAGE_1_DONE

    def test_complete_production_standard_flow(self, service, setup_data):
        # Tworzymy produkcję już po Etapie 1
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.STAGE_1_DONE
        )

        success, msg = service.complete_production(production.id)
        assert success is True

        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.COMPLETED
        assert production.completed_at is not None

        # SPRAWDZAMY CZY MAGAZYN FAKTYCZNIE SPADŁ
        dashboard = service.get_inventory_dashboard()['inventory']
        bin_stock = next(i for i in dashboard if i.ingredient_id == setup_data['ing_bin'].id).current_stock
        # 1000 - 800 = 200
        assert bin_stock == Decimal('200.00')

    def test_complete_production_skip_stages(self, service, setup_data):
        # Tworzymy produkcję prosto w kolejce
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=500,
            status=ProductionModel.Statuses.QUEUED
        )

        # Wymuszamy zakończenie z pominięciem etapów (checkbox "Od razu zatwierdź")
        success, msg = service.complete_production(production.id, skip_stages=True)
        assert success is True

        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.COMPLETED

    def test_complete_production_blocks_if_no_stock(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=5000,  # Za dużo
            status=ProductionModel.Statuses.STAGE_1_DONE
        )

        success, msg = service.complete_production(production.id)
        assert success is False
        assert "Brak wystarczającej ilości" in msg

        # Upewniamy się, że status się NIE zmienił
        production.refresh_from_db()
        assert production.status == ProductionModel.Statuses.STAGE_1_DONE

    def test_get_production_details_for_stages_splits_bin_and_bag_items(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.QUEUED
        )

        details = service.get_production_details_for_stages(production.id)

        assert details['production'] == production
        assert details['stage1_items'][0]['name'] == "Kukurydza"
        assert details['stage1_items'][0]['weight_kg'] == Decimal('800.00')
        assert details['stage2_items'][0]['name'] == "Koncentrat"
        assert details['stage2_items'][0]['weight_kg'] == Decimal('200.00')

    def test_process_stage_1_rejects_non_queued_production(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=1000,
            status=ProductionModel.Statuses.STAGE_1_DONE
        )

        success, message = service.process_production_stage_1(production.id)

        assert success is False
        assert "kolejce początkowej" in message

    def test_complete_production_rejects_before_stage_1(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=100,
            status=ProductionModel.Statuses.QUEUED
        )

        success, message = service.complete_production(production.id)

        assert success is False
        assert "przed wykonaniem Etapu 1" in message

    def test_complete_production_rejects_already_completed(self, service, setup_data):
        production = ProductionModel.objects.create(
            date=timezone.now().date(),
            recipe=setup_data['recipe'],
            quantity_kg=100,
            status=ProductionModel.Statuses.COMPLETED
        )

        success, message = service.complete_production(production.id, skip_stages=True)

        assert success is False
        assert "wcześniej zaksięgowane" in message

    def test_get_calculator_data_returns_recipe_costs(self, service, setup_data):
        from feed.models import IngredientPriceConfigModel

        IngredientPriceConfigModel.objects.create(
            ingredient=setup_data['ing_bin'],
            price_per_kg=Decimal('1.00')
        )
        IngredientPriceConfigModel.objects.create(
            ingredient=setup_data['ing_bag'],
            price_per_kg=Decimal('3.00')
        )

        costs = service.get_calculator_data()

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
        DeliveryModel.objects.create(
            ingredient=low_threshold_ingredient,
            date=timezone.now().date(),
            quantity_kg=Decimal('600.00'),
            price_per_kg=Decimal('1.00'),
        )
        DeliveryModel.objects.create(
            ingredient=enough_stock_ingredient,
            date=timezone.now().date(),
            quantity_kg=Decimal('600.00'),
            price_per_kg=Decimal('1.00'),
        )

        service = FeedManagementService(farm=farm)
        dashboard = service.get_inventory_dashboard()

        alert_ids = [item.ingredient_id for item in dashboard['low_stock_alerts']]
        assert alert_ids == [low_threshold_ingredient.id]
        assert dashboard['low_stock_alerts'][0].low_stock_threshold_kg == Decimal('750.00')
        assert service.get_default_production_quantity() == Decimal('1800.00')
