"""
URL configuration for managerGospodarstwa project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

from farms.views import global_search_view
from managerGospodarstwa.admin_backup import admin_database_backup_view, admin_database_restore_view

admin.site.index_template = 'admin/custom_index.html'

urlpatterns = [
    path('admin/kopia-zapasowa-bazy/', admin_database_backup_view, name='admin_database_backup'),
    path('admin/przywroc-kopie-bazy/', admin_database_restore_view, name='admin_database_restore'),
    path('admin/', admin.site.urls),
    path('szukaj/', global_search_view, name='global_search'),
    path('', include('sows.urls')),
    path('ustawienia/', include('farms.urls')),
    path('sprzedaz/', include('sales.urls')),
    path('pasza/', include('feed.urls')),
    path('koszty/', include('costs.urls')),
]
