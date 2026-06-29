def current_farm(request):
    farm = getattr(request, 'farm', None)
    context = {'current_farm': farm, 'ui_modules': [], 'ui_visible_module_keys': []}
    if getattr(request, 'user', None) and request.user.is_authenticated and farm:
        from farms.services.module_navigation import ModuleNavigationService

        active = getattr(getattr(request, 'resolver_match', None), 'url_name', '')
        service = ModuleNavigationService(farm, active)
        modules = service.modules()
        context['ui_modules'] = modules
        context['ui_module_groups'] = service.grouped_modules(modules)
        context['ui_primary_modules'] = service.primary_modules(modules)
        context['ui_mobile_modules'] = service.mobile_modules(modules)
        context['ui_visible_module_keys'] = service.visible_keys()
    return context
