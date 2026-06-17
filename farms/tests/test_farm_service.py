import json
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.test import RequestFactory
from django.urls import reverse

from farms.context_processors import current_farm
from farms.middleware import CurrentFarmMiddleware
from farms.models import FarmModel, FarmSettingsModel
from farms.services.current_farm import get_current_farm
from farms.services.farm_service import get_default_farm_name, get_first_user_farm, get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from feed.models import IngredientModel


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


@pytest.mark.django_db
def test_get_current_farm_reuses_request_farm():
    user = User.objects.create_user(username='request-farm-user')
    farm = get_or_create_user_farm(user)
    request = RequestFactory().get('/')
    request.user = user
    request.farm = farm

    assert get_current_farm(request) == farm


@pytest.mark.django_db
def test_get_farm_settings_creates_default_settings():
    user = User.objects.create_user(username='settings-user')
    farm = get_or_create_user_farm(user)

    settings = get_farm_settings(farm)

    assert settings.farm == farm
    assert settings.pregnancy_check_after_days == 30
    assert settings.gestation_days == 114
    assert FarmSettingsModel.objects.filter(farm=farm).count() == 1


@pytest.mark.django_db
def test_farm_settings_view_updates_farm_and_rules(client):
    user = User.objects.create_user(username='settings-view-user', password='password')
    farm = get_or_create_user_farm(user)
    client.login(username='settings-view-user', password='password')

    response = client.post(reverse('farm_settings'), {
        'farm_name': 'Nowa nazwa gospodarstwa',
        'pregnancy_check_after_days': '28',
        'gestation_days': '115',
        'farrowing_alert_days_ahead': '5',
        'vaccination_alert_days_ahead': '9',
        'default_production_quantity_kg': '1800.00',
        'allow_farrowing_without_pregnancy_check': 'on',
        'ask_before_auto_pregnancy_check': 'on',
    })

    assert response.status_code == 302
    farm.refresh_from_db()
    settings = get_farm_settings(farm)
    assert farm.name == 'Nowa nazwa gospodarstwa'
    assert settings.pregnancy_check_after_days == 28
    assert settings.farrowing_alert_days_ahead == 5


@pytest.mark.django_db
def test_user_data_export_contains_only_current_farm_data(client):
    user = User.objects.create_user(username='export-user', password='password')
    farm = get_or_create_user_farm(user)
    other_user = User.objects.create_user(username='other-export-user')
    other_farm = get_or_create_user_farm(other_user)

    own_ingredient = IngredientModel.objects.create(name='Własna soja', farm=farm)
    IngredientModel.objects.create(name='Cudza soja', farm=other_farm)

    client.login(username='export-user', password='password')
    response = client.get(reverse('export_user_data'))

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/zip'

    with ZipFile(BytesIO(response.content)) as export_zip:
        exported_file = export_zip.namelist()[0]
        payload = json.loads(export_zip.read(exported_file).decode('utf-8'))

    exported_ingredients = payload['data']['feed.IngredientModel']
    assert len(exported_ingredients) == 1
    assert exported_ingredients[0]['pk'] == own_ingredient.id
    assert exported_ingredients[0]['fields']['name'] == 'Własna soja'
