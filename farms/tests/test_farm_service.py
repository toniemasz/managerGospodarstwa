import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory

from farms.context_processors import current_farm
from farms.middleware import CurrentFarmMiddleware
from farms.models import FarmModel
from farms.services.farm_service import get_default_farm_name, get_first_user_farm, get_or_create_user_farm


@pytest.mark.django_db
def test_get_default_farm_name_uses_username_when_full_name_missing():
    user = User.objects.create_user(username='jan')

    assert get_default_farm_name(user) == 'Gospodarstwo jan'


@pytest.mark.django_db
def test_get_or_create_user_farm_creates_and_reuses_farm():
    user = User.objects.create_user(username='anna')

    first = get_or_create_user_farm(user)
    second = get_or_create_user_farm(user)

    assert first == second
    assert first.owner == user
    assert first.name == 'Gospodarstwo anna'
    assert FarmModel.objects.count() == 1


@pytest.mark.django_db
def test_get_or_create_user_farm_ignores_anonymous_users():
    assert get_or_create_user_farm(AnonymousUser()) is None


@pytest.mark.django_db
def test_get_first_user_farm_returns_first_users_farm():
    first_user = User.objects.create_user(username='first')
    User.objects.create_user(username='second')

    farm = get_first_user_farm()

    assert farm.owner == first_user


@pytest.mark.django_db
def test_current_farm_middleware_sets_request_farm():
    user = User.objects.create_user(username='middleware-user')
    request = RequestFactory().get('/')
    request.user = user

    response = CurrentFarmMiddleware(lambda req: req)(request)

    assert response.farm.owner == user


@pytest.mark.django_db
def test_current_farm_context_processor_exposes_request_farm():
    user = User.objects.create_user(username='context-user')
    farm = get_or_create_user_farm(user)
    request = RequestFactory().get('/')
    request.farm = farm

    assert current_farm(request) == {'current_farm': farm}
