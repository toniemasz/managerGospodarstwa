from django.urls import path

from farms.views import farm_settings_view


urlpatterns = [
    path('', farm_settings_view, name='farm_settings'),
]
