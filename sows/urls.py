# sows/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    modules_home_view,
    dashboard_view,
    add_sow_view,
    sow_detail_view,
    add_event_view,
    delete_sow_view,
    edit_event_view,
    delete_event_view,
    bulk_vaccinate_view,
    bulk_pregnancy_check_view,
    add_vaccination_plan_view

)

urlpatterns = [
    path('', modules_home_view, name='modules_home'),
    path('maciory/', dashboard_view, name='dashboard'),
    path('maciory/dodaj/', add_sow_view, name='add_sow'),
    path('maciory/<int:sow_id>/usun/', delete_sow_view, name='delete_sow'),
    path('zdarzenie/<int:event_id>/edytuj/', edit_event_view, name='edit_event'),
    path('zdarzenie/<int:event_id>/usun/', delete_event_view, name='delete_event'),


    path('maciory/<int:sow_id>/', sow_detail_view, name='sow_detail'),
    path('maciory/szczepienie-grupowe/', bulk_vaccinate_view, name='bulk_vaccinate'),
    path('maciory/badania-grupowe/', bulk_pregnancy_check_view, name='bulk_pregnancy_check'),
    path('maciory/<int:sow_id>/zdarzenie/dodaj/', add_event_view, name='add_event'),

    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('konfiguracja/szczepienie/dodaj/', add_vaccination_plan_view, name='add_vaccination_plan'),
]