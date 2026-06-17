from farms.services.farm_service import get_or_create_user_farm


def get_current_farm(request):
    farm = getattr(request, 'farm', None)
    if farm is None and request.user.is_authenticated:
        farm = get_or_create_user_farm(request.user)
        request.farm = farm
    return farm
