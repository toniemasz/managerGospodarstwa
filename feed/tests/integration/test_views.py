import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal
from django.utils import timezone
from unittest.mock import patch

from farms.services.farm_service import get_or_create_user_farm
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.actions.inventory import InventoryActions


@pytest.fixture
def auth_client(client):
    user = User.objects.create_user(username='tester', password='password')
    client.user = user
    client.farm = get_or_create_user_farm(user)
    client.login(username='tester', password='password')
    return client


@pytest.mark.django_db
def test_feed_inventory_view_requires_login(client):
    url = reverse('feed_inventory')
    response = client.get(url)
    # Powinno przekierować do logowania (HTTP 302)
    assert response.status_code == 302
    assert 'login' in response.url


@pytest.mark.django_db
def test_feed_inventory_view_loads_for_authenticated_user(auth_client):
    url = reverse('feed_inventory')
    response = auth_client.get(url)

    assert response.status_code == 200
    assert 'inventory' in response.context
    assert 'low_stock_alerts' in response.context
    assert 'feed/inventory.html' in [t.name for t in response.templates]


@pytest.mark.django_db
def test_feed_recipes_view_loads_successfully(auth_client):
    url = reverse('feed_recipes')
    response = auth_client.get(url)
    assert response.status_code == 200
    assert 'feed/recipes.html' in [t.name for t in response.templates]


@pytest.fixture
def feed_objects(auth_client):
    farm = auth_client.farm
    ingredient = IngredientModel.objects.create(name="Kukurydza", is_in_bin=True, farm=farm)
    delivery = DeliveryModel.objects.create(
        ingredient=ingredient,
        date=timezone.now().date(),
        quantity_kg=Decimal('1000.00'),
        price_per_kg=Decimal('1.00000'),
    )
    InventoryActions(farm).sync_delivery(delivery)
    recipe = RecipeModel.objects.create(name="Widokowa", farm=farm)
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal('100.00'))
    production = ProductionModel.objects.create(
        date=timezone.now().date(),
        recipe=recipe,
        quantity_kg=Decimal('100.00'),
        status=ProductionModel.Statuses.QUEUED,
    )
    return {
        'ingredient': ingredient,
        'delivery': delivery,
        'recipe': recipe,
        'production': production,
    }


@pytest.mark.django_db
@pytest.mark.parametrize("route_name, key, template", [
    ('ingredient_list', None, 'feed/ingredients.html'),
    ('add_ingredient', None, 'feed/form_generic.html'),
    ('edit_ingredient', 'ingredient', 'feed/form_generic.html'),
    ('feed_inventory', None, 'feed/inventory.html'),
    ('add_delivery', None, 'feed/form_generic.html'),
    ('edit_delivery', 'delivery', 'feed/form_generic.html'),
    ('feed_recipes', None, 'feed/recipes.html'),
    ('add_recipe', None, 'feed/add_recipe.html'),
    ('edit_recipe', 'recipe', 'feed/add_recipe.html'),
    ('feed_productions', None, 'feed/productions.html'),
    ('add_production', None, 'feed/production_form.html'),
    ('edit_production', 'production', 'feed/production_form.html'),
    ('process_stage1', 'production', 'feed/stage1.html'),
    ('feed_calculator', None, 'feed/calculator.html'),
    ('feed_full_inventory', None, 'feed/full_inventory.html'),
])
def test_feed_get_views_load(auth_client, feed_objects, route_name, key, template):
    args = [feed_objects[key].id] if key else []
    response = auth_client.get(reverse(route_name, args=args))

    assert response.status_code == 200
    assert template in [t.name for t in response.templates]


@pytest.mark.django_db
def test_add_recipe_does_not_save_when_formset_invalid(auth_client, feed_objects):
    response = auth_client.post(reverse('add_recipe'), {
        'name': 'Niepełna',
        'items-TOTAL_FORMS': '1',
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-ingredient': feed_objects['ingredient'].id,
        'items-0-percentage': '90.00',
    })

    assert response.status_code == 200
    assert not RecipeModel.objects.filter(name='Niepełna').exists()


@pytest.mark.django_db
def test_edit_recipe_removes_selected_ingredient(auth_client):
    farm = auth_client.farm
    recipe = RecipeModel.objects.create(name='Receptura do zmiany', farm=farm)
    wheat = IngredientModel.objects.create(name='Pszenica usuwana', farm=farm)
    soy = IngredientModel.objects.create(name='Soja po zmianie', farm=farm)
    wheat_item = RecipeItemModel.objects.create(recipe=recipe, ingredient=wheat, percentage=Decimal('60.00'))
    soy_item = RecipeItemModel.objects.create(recipe=recipe, ingredient=soy, percentage=Decimal('40.00'))

    response = auth_client.post(reverse('edit_recipe', args=[recipe.id]), {
        'name': recipe.name,
        'items-TOTAL_FORMS': '2',
        'items-INITIAL_FORMS': '2',
        'items-MIN_NUM_FORMS': '0',
        'items-MAX_NUM_FORMS': '1000',
        'items-0-id': wheat_item.id,
        'items-0-ingredient': wheat.id,
        'items-0-percentage': '60.00',
        'items-0-DELETE': 'on',
        'items-1-id': soy_item.id,
        'items-1-ingredient': soy.id,
        'items-1-percentage': '100.00',
    })

    assert response.status_code == 302
    assert not RecipeItemModel.objects.filter(id=wheat_item.id).exists()
    soy_item.refresh_from_db()
    assert soy_item.percentage == Decimal('100.00')


@pytest.mark.django_db
def test_feed_post_create_and_delete_views(auth_client, feed_objects):
    add_ingredient = auth_client.post(reverse('add_ingredient'), {
        'name': 'Soja',
        'description': '',
        'low_stock_threshold_kg': '250.00',
        'is_in_bin': '',
    })
    assert add_ingredient.status_code == 302
    soja = IngredientModel.objects.get(name='Soja')
    assert soja.farm == auth_client.farm
    assert soja.low_stock_threshold_kg == Decimal('250.00')

    add_delivery = auth_client.post(reverse('add_delivery'), {
        'date': timezone.now().date(),
        'ingredient': soja.id,
        'quantity_kg': '50.00',
        'price_per_kg': '2.00000',
    })
    assert add_delivery.status_code == 302
    delivery = DeliveryModel.objects.get(ingredient=soja)

    delete_delivery = auth_client.post(reverse('delete_delivery', args=[delivery.id]))
    assert delete_delivery.status_code == 302
    assert not DeliveryModel.objects.filter(id=delivery.id).exists()

    delete_ingredient = auth_client.post(reverse('delete_ingredient', args=[soja.id]))
    assert delete_ingredient.status_code == 302
    assert not IngredientModel.objects.filter(id=soja.id).exists()


@pytest.mark.django_db
def test_recipe_delete_view_deletes_unused_recipe_and_protects_used_recipe(auth_client, feed_objects):
    unused_recipe = RecipeModel.objects.create(name='Receptura bez śrutowania', farm=auth_client.farm)

    deleted = auth_client.post(reverse('delete_recipe', args=[unused_recipe.id]))

    assert deleted.status_code == 302
    assert not RecipeModel.objects.filter(id=unused_recipe.id).exists()

    used_recipe = feed_objects['recipe']
    protected = auth_client.post(reverse('delete_recipe', args=[used_recipe.id]))

    assert protected.status_code == 302
    assert RecipeModel.objects.filter(id=used_recipe.id).exists()


@pytest.mark.django_db
def test_ingredient_delete_view_protects_ingredient_used_in_recipe(auth_client, feed_objects):
    ingredient = feed_objects['ingredient']

    response = auth_client.post(reverse('delete_ingredient', args=[ingredient.id]))

    assert response.status_code == 302
    assert IngredientModel.objects.filter(id=ingredient.id).exists()


@pytest.mark.django_db
def test_feed_production_post_actions(auth_client, feed_objects):
    response = auth_client.post(reverse('add_production'), {
        'date': timezone.now().date(),
        'time': '08:30',
        'recipe': feed_objects['recipe'].id,
        'quantity_kg': '25.00',
    })
    assert response.status_code == 302

    production = ProductionModel.objects.exclude(id=feed_objects['production'].id).get()
    edit = auth_client.post(reverse('edit_production', args=[production.id]), {
        'date': timezone.now().date(),
        'time': '09:00',
        'recipe': feed_objects['recipe'].id,
        'quantity_kg': '30.00',
    })
    assert edit.status_code == 302

    stage1 = auth_client.post(reverse('process_stage1', args=[production.id]))
    assert stage1.status_code == 302
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.STAGE_1_DONE

    stage2 = auth_client.post(reverse('process_stage2', args=[production.id]), {'force_inventory': 'on'})
    assert stage2.status_code == 302
    production.refresh_from_db()
    assert production.status == ProductionModel.Statuses.COMPLETED

    delete_completed = auth_client.post(reverse('delete_production', args=[production.id]))
    assert delete_completed.status_code == 302
    assert not ProductionModel.objects.filter(id=production.id).exists()

    queued = feed_objects['production']
    delete = auth_client.post(reverse('delete_production', args=[queued.id]))
    assert delete.status_code == 302
    assert not ProductionModel.objects.filter(id=queued.id).exists()


@pytest.mark.django_db
def test_add_queued_production_does_not_touch_inventory_release(auth_client, feed_objects):
    response = auth_client.post(reverse('add_production'), {
        'date': timezone.now().date(),
        'time': '08:30',
        'recipe': feed_objects['recipe'].id,
        'quantity_kg': '25.00',
    })

    assert response.status_code == 302
    production = ProductionModel.objects.get(
        recipe=feed_objects['recipe'],
        quantity_kg=Decimal('25.00'),
        status=ProductionModel.Statuses.QUEUED,
    )
    assert not production.ingredient_usages.exists()


@pytest.mark.django_db
def test_feed_views_show_only_current_farm_data(auth_client):
    other_user = User.objects.create_user(username='other-feed', password='password')
    other_farm = get_or_create_user_farm(other_user)

    IngredientModel.objects.create(name='Własna pszenica', farm=auth_client.farm)
    IngredientModel.objects.create(name='Cudza pszenica', farm=other_farm)

    response = auth_client.get(reverse('ingredient_list'))

    assert response.status_code == 200
    assert 'Własna pszenica' in response.content.decode()
    assert 'Cudza pszenica' not in response.content.decode()


@pytest.mark.django_db
def test_recipe_detail_shows_completed_production_for_selected_year(auth_client, feed_objects):
    recipe = feed_objects['recipe']
    DeliveryModel.objects.create(
        ingredient=feed_objects['ingredient'],
        date=timezone.datetime(2026, 1, 1).date(),
        quantity_kg=Decimal('20000.00'),
        price_per_kg=Decimal('1.00000'),
    )
    ProductionModel.objects.create(
        date=timezone.datetime(2026, 4, 1).date(),
        recipe=recipe,
        quantity_kg=Decimal('18450.00'),
        status=ProductionModel.Statuses.COMPLETED,
    )
    ProductionModel.objects.create(
        date=timezone.datetime(2025, 4, 1).date(),
        recipe=recipe,
        quantity_kg=Decimal('1000.00'),
        status=ProductionModel.Statuses.QUEUED,
    )

    response = auth_client.get(reverse('recipe_detail', args=[recipe.id]), {'year': '2026'})

    assert response.status_code == 200
    assert response.context['yearly_production']['year'] == 2026
    assert response.context['yearly_production']['quantity_t'] == Decimal('18.45')
    assert 'Wyprodukowano w 2026 roku' in response.content.decode()


@pytest.mark.django_db
def test_feed_calculator_rejects_invalid_price_override(auth_client, feed_objects):
    ingredient = feed_objects['ingredient']

    response = auth_client.post(reverse('feed_calculator'), {
        f'price_{ingredient.id}': 'nie-liczba',
    })

    assert response.status_code == 200
    content = response.content.decode()
    assert "Podaj poprawną cenę składnika" in content
    assert "Nie przeliczono kosztu paszy" in content
    assert response.context['costs'][0].cost_per_kg == Decimal('1.00000')


@pytest.mark.django_db
def test_feed_calculator_marks_missing_delivery_price(auth_client):
    IngredientModel.objects.create(name='Bez ceny', farm=auth_client.farm)

    response = auth_client.get(reverse('feed_calculator'))

    assert response.status_code == 200
    assert "Brak zakupu, brak ceny" in response.content.decode()
