import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import override_settings

from feed.models import IngredientModel, ProductionModel, RecipeModel
from sales.models import PigSaleModel
from sows.models import SowModel


@pytest.mark.django_db(transaction=True)
@override_settings(DEBUG=True)
def test_seed_demo_data_creates_realistic_idempotent_dataset():
    call_command("seed_demo_data", verbosity=0)
    user = get_user_model().objects.get(username="testtest")
    assert user.check_password("testtest")
    farm = user.farm
    counts = (
        SowModel.objects.filter(farm=farm).count(),
        IngredientModel.objects.filter(farm=farm).count(),
        RecipeModel.objects.filter(farm=farm).count(),
        ProductionModel.objects.filter(recipe__farm=farm).count(),
        PigSaleModel.objects.filter(farm=farm).count(),
    )
    assert counts == (40, 15, 6, 20, 12)
    call_command("seed_demo_data", verbosity=0)
    assert counts == (
        SowModel.objects.filter(farm=farm).count(),
        IngredientModel.objects.filter(farm=farm).count(),
        RecipeModel.objects.filter(farm=farm).count(),
        ProductionModel.objects.filter(recipe__farm=farm).count(),
        PigSaleModel.objects.filter(farm=farm).count(),
    )


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_seed_demo_data_is_blocked_outside_debug():
    with pytest.raises(CommandError):
        call_command("seed_demo_data", verbosity=0)
    with pytest.raises(CommandError):
        call_command("seed_demo_data", "--reset", verbosity=0)


@pytest.mark.django_db(transaction=True)
@override_settings(DEBUG=True)
def test_seed_demo_data_reset_clears_local_database():
    get_user_model().objects.create_user(username="old-local-user")
    call_command("seed_demo_data", "--reset", verbosity=0)
    assert not get_user_model().objects.filter(username="old-local-user").exists()
    assert get_user_model().objects.filter(username="testtest").exists()
