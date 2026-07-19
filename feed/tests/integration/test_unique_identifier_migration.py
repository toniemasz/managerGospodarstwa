from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_feed_identifier_migration_suffixes_names_and_consolidates_recipe_items():
    executor = MigrationExecutor(connection)
    old_target = [('feed', '0011_protect_production_dependencies')]
    new_target = [('feed', '0012_normalized_business_identifiers')]
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps

    User = old_apps.get_model('auth', 'User')
    Farm = old_apps.get_model('farms', 'FarmModel')
    Ingredient = old_apps.get_model('feed', 'IngredientModel')
    Recipe = old_apps.get_model('feed', 'RecipeModel')
    RecipeItem = old_apps.get_model('feed', 'RecipeItemModel')
    Product = old_apps.get_model('feed', 'FeedProductModel')

    owner = User.objects.create(username='feed-identifier-migration')
    farm = Farm.objects.create(owner=owner, name='Migracja paszy')
    first_ingredient = Ingredient.objects.create(farm=farm, name='Soja')
    Ingredient.objects.create(farm=farm, name=' soja ')
    recipe = Recipe.objects.create(farm=farm, name='Starter')
    Recipe.objects.create(farm=farm, name=' starter ')
    Product.objects.create(farm=farm, name='Grower', source_type='PURCHASED_READY')
    Product.objects.create(farm=farm, name=' grower ', source_type='PURCHASED_READY')
    RecipeItem.objects.create(
        recipe=recipe,
        ingredient=first_ingredient,
        percentage=Decimal('40.00'),
    )
    RecipeItem.objects.create(
        recipe=recipe,
        ingredient=first_ingredient,
        percentage=Decimal('60.00'),
    )

    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    new_apps = executor.loader.project_state(new_target).apps
    NewIngredient = new_apps.get_model('feed', 'IngredientModel')
    NewRecipe = new_apps.get_model('feed', 'RecipeModel')
    NewRecipeItem = new_apps.get_model('feed', 'RecipeItemModel')
    NewProduct = new_apps.get_model('feed', 'FeedProductModel')

    assert list(NewIngredient.objects.values_list('name', flat=True).order_by('id')) == [
        'Soja',
        'soja (1)',
    ]
    assert list(NewRecipe.objects.values_list('name', flat=True).order_by('id')) == [
        'Starter',
        'starter (1)',
    ]
    assert list(NewProduct.objects.values_list('name', flat=True).order_by('id')) == [
        'Grower',
        'grower (1)',
    ]
    assert NewRecipeItem.objects.get().percentage == Decimal('100.00')

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
