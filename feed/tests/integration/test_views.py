import pytest
from django.urls import reverse
from django.contrib.auth.models import User


@pytest.fixture
def auth_client(client):
    user = User.objects.create_user(username='tester', password='password')
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