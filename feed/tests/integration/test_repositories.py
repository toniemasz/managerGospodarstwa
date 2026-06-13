import pytest
from decimal import Decimal
from django.utils import timezone

from feed.services.feed_management_service import FeedManagementService
from feed.models import IngredientModel, DeliveryModel, RecipeModel, RecipeItemModel, ProductionModel, \
    IngredientPriceConfigModel
from feed.services.feed_repository import FeedRepository
from farms.models import FarmModel
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_repository_calculates_inventory_state_correctly():
    # Arrange
    ing = IngredientModel.objects.create(name="Kukurydza")
    DeliveryModel.objects.create(
        ingredient=ing,
        date=timezone.now().date(),
        quantity_kg=Decimal('2000.00'),
        price_per_kg=Decimal('1.0')
    )

    recipe = RecipeModel.objects.create(name="Testowa 100")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))

    # Symulujemy zużycie
    ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('500.00'),
        status=ProductionModel.Statuses.COMPLETED
    )

    # Act
    service = FeedManagementService()
    dashboard = service.get_inventory_dashboard()['inventory']

    # Assert
    kukurydza_stock = next(i for i in dashboard if i.ingredient_id == ing.id).current_stock
    assert kukurydza_stock == Decimal('1500.00')  # 2000 dostarczono - 500 zużyto


@pytest.mark.django_db
def test_repository_fetches_raw_data_for_calculator():
    # Arrange
    ing = IngredientModel.objects.create(name="Soja")
    recipe = RecipeModel.objects.create(name="Testowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    IngredientPriceConfigModel.objects.create(ingredient=ing, price_per_kg=Decimal('2.50'))

    repo = FeedRepository()

    prices = repo.get_ingredient_prices_map()

    assert prices[ing.id] == Decimal('2.50')

    recipes = repo.get_recipes_with_items()

    assert len(recipes) == 1
    assert recipes[0].items.first().ingredient == ing


@pytest.mark.django_db
def test_repository_public_methods_for_production_flow():
    ing = IngredientModel.objects.create(name="Pszenica")
    recipe = RecipeModel.objects.create(name="Pełnoporcjowa")
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ing, percentage=Decimal('100.00'))
    queued = ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('100.00'),
        status=ProductionModel.Statuses.QUEUED,
    )
    completed = ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('200.00'),
        status=ProductionModel.Statuses.COMPLETED,
    )
    repo = FeedRepository()

    assert list(repo.get_all_ingredients()) == [ing]
    assert list(repo.get_completed_productions()) == [completed]

    fetched = repo.get_production_for_processing(queued.id)
    assert fetched.id == queued.id

    fetched.status = ProductionModel.Statuses.STAGE_1_DONE
    repo.save_production(fetched)
    queued.refresh_from_db()
    assert queued.status == ProductionModel.Statuses.STAGE_1_DONE


@pytest.mark.django_db
def test_repository_filters_data_by_farm():
    owner = User.objects.create_user(username='feed-owner')
    other = User.objects.create_user(username='feed-other')
    farm = FarmModel.objects.create(owner=owner, name='Gospodarstwo testowe')
    other_farm = FarmModel.objects.create(owner=other, name='Inne gospodarstwo')

    own_ingredient = IngredientModel.objects.create(name='Własny składnik', farm=farm)
    IngredientModel.objects.create(name='Cudzy składnik', farm=other_farm)

    repo = FeedRepository(farm=farm)

    assert list(repo.get_all_ingredients()) == [own_ingredient]
