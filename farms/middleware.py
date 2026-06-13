from farms.services.farm_service import get_or_create_user_farm


class CurrentFarmMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.farm = get_or_create_user_farm(request.user)
        return self.get_response(request)
