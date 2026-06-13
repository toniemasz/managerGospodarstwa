def current_farm(request):
    return {'current_farm': getattr(request, 'farm', None)}
