from django.contrib.auth import get_user_model

from farms.models import FarmModel

LEGACY_FARM_USERNAME = 'gospodarstwo'


def get_default_farm_name(user) -> str:
    display_name = user.get_full_name() or user.get_username()
    return f"Gospodarstwo {display_name}"


def get_or_create_user_farm(user) -> FarmModel | None:
    if not user or not user.is_authenticated:
        return None

    farm, _ = FarmModel.objects.get_or_create(
        owner=user,
        defaults={'name': get_default_farm_name(user)},
    )
    return farm


def get_first_user_farm() -> FarmModel | None:
    User = get_user_model()
    user = User.objects.exclude(username=LEGACY_FARM_USERNAME).order_by('id').first()
    if not user:
        return None
    return get_or_create_user_farm(user)


def get_or_create_legacy_farm() -> FarmModel:
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=LEGACY_FARM_USERNAME,
        defaults={
            'first_name': 'Dane',
            'last_name': 'historyczne',
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])

    farm, _ = FarmModel.objects.get_or_create(
        owner=user,
        defaults={'name': 'Gospodarstwo'},
    )
    return farm
