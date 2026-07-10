def _interface_scale(settings):
    scale = getattr(settings, "interface_scale", "standard") or "standard"
    if scale == "large":
        return "comfortable"
    return scale if scale in {"compact", "standard", "comfortable"} else "standard"


def _theme(settings):
    theme = getattr(settings, "theme", "light") or "light"
    return theme if theme in {"light", "dark", "system"} else "light"


def _font_scale(settings):
    try:
        scale = int(getattr(settings, "font_scale", 100) or 100)
    except (TypeError, ValueError):
        scale = 100
    return str(min(200, max(20, scale)))


def _topbar_notifications(farm):
    from datetime import date

    from django.urls import reverse

    from farms.services.cache import TOPBAR_NOTIFICATIONS_TTL, cached_farm_value
    from farms.services.task_center import TaskCenterService

    def build_notifications():
        priority_order = {"urgent": 0, "today": 1, "upcoming": 2}
        task_summary = TaskCenterService(farm).get_tasks()
        items = [
            item
            for tab in task_summary["tab_list"]
            for section in tab["sections"]
            for item in section["items"]
        ]
        items.sort(key=lambda item: (priority_order.get(item["priority"], 9), item.get("due_date") or date.max))
        return [
            {
                **item,
                "url": item.get("object_url") or item.get("action_url") or reverse("task_center"),
            }
            for item in items[:6]
        ], len(items)

    return cached_farm_value(
        farm,
        "topbar_notifications",
        (),
        timeout=TOPBAR_NOTIFICATIONS_TTL,
        builder=build_notifications,
    )


def current_farm(request):
    farm = getattr(request, 'farm', None)
    context = {
        'current_farm': farm,
        'ui_modules': [],
        'ui_visible_module_keys': [],
        'ui_interface_scale': 'standard',
        'ui_theme': 'light',
        'ui_font_scale': '100',
        'ui_font_scale_ratio': '1',
        'ui_notifications': [],
        'ui_notification_count': 0,
        'ui_notification_more_count': 0,
    }
    if getattr(request, 'user', None) and request.user.is_authenticated and farm:
        from farms.services.module_navigation import ModuleNavigationService
        from farms.services.settings_service import get_farm_settings

        active = getattr(getattr(request, 'resolver_match', None), 'url_name', '')
        settings = get_farm_settings(farm)
        service = ModuleNavigationService(farm, active)
        modules = service.modules()
        notifications, notification_count = _topbar_notifications(farm)
        context['ui_modules'] = modules
        context['ui_module_groups'] = service.grouped_modules(modules)
        context['ui_primary_modules'] = service.primary_modules(modules)
        context['ui_mobile_modules'] = service.mobile_modules(modules)
        context['ui_visible_module_keys'] = service.visible_keys()
        context['ui_interface_scale'] = _interface_scale(settings)
        context['ui_theme'] = _theme(settings)
        context['ui_font_scale'] = _font_scale(settings)
        context['ui_font_scale_ratio'] = str(int(context['ui_font_scale']) / 100).rstrip('0').rstrip('.')
        context['ui_notifications'] = notifications
        context['ui_notification_count'] = notification_count
        context['ui_notification_more_count'] = max(0, notification_count - len(notifications))
    return context
