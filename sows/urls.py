
from django.urls import path
from django.contrib.auth import views as auth_views
from .views import dashboard_view, modules_home_view

urlpatterns = [
    path('', modules_home_view, name='modules_home'),  # Nowa strona główna
    path('maciory/', dashboard_view, name='dashboard'),  # Przeniesiony dashboard

    path('login/', auth_views.LoginView.as_pretrained() if hasattr(auth_views.LoginView,
                                                                   'as_pretrained') else auth_views.LoginView.as_view(
        template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
]