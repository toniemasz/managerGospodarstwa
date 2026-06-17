from django.urls import path

from farms.views import export_user_data_view, farm_settings_view


urlpatterns = [
    path('', farm_settings_view, name='farm_settings'),
    path('eksport-danych/', export_user_data_view, name='export_user_data'),
]
