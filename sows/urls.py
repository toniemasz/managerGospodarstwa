# sows/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from .views import (
    modules_home_view,
    dashboard_view,
    add_sow_view,
    edit_sow_view,
    sow_detail_view,
    add_event_view,
    delete_sow_view,
    edit_event_view,
    delete_event_view,
    bulk_vaccinate_view,
    bulk_pregnancy_check_view,
    bulk_sow_events_view,
    vaccination_plans_view,
    add_vaccination_plan_view,
    edit_vaccination_plan_view,
    delete_vaccination_plan_view,
    archived_sows_view,
    general_statistics_view

)

urlpatterns = [
    path('', modules_home_view, name='modules_home'),
    path('maciory/', dashboard_view, name='dashboard'),
    path('maciory/dodaj/', add_sow_view, name='add_sow'),
    path('maciory/<int:sow_id>/edytuj/', edit_sow_view, name='edit_sow'),
    path('maciory/<int:sow_id>/usun/', delete_sow_view, name='delete_sow'),
    path('zdarzenie/<int:event_id>/edytuj/', edit_event_view, name='edit_event'),
    path('zdarzenie/<int:event_id>/usun/', delete_event_view, name='delete_event'),

    path('maciory/archiwum/', archived_sows_view, name='archived_sows'),
    path('maciory/<int:sow_id>/', sow_detail_view, name='sow_detail'),
    path('maciory/szczepienie-grupowe/', bulk_vaccinate_view, name='bulk_vaccinate'),
    path('maciory/badania-grupowe/', bulk_pregnancy_check_view, name='bulk_pregnancy_check'),
    path('maciory/zdarzenia/masowo/', bulk_sow_events_view, name='bulk_sow_events'),
    path('maciory/<int:sow_id>/zdarzenie/dodaj/', add_event_view, name='add_event'),
    path('maciory/statystyki/', general_statistics_view, name='general_statistics'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('konfiguracja/szczepienia/', vaccination_plans_view, name='vaccination_plans'),
    path('konfiguracja/szczepienie/dodaj/', add_vaccination_plan_view, name='add_vaccination_plan'),
    path('konfiguracja/szczepienie/<int:plan_id>/edytuj/', edit_vaccination_plan_view, name='edit_vaccination_plan'),
    path('konfiguracja/szczepienie/<int:plan_id>/usun/', delete_vaccination_plan_view, name='delete_vaccination_plan'),
]
