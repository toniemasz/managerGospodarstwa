from django.urls import path
from .views import sales_list_view, add_sale_view, edit_sale_view, delete_sale_view

urlpatterns = [
    path('', sales_list_view, name='sales_list'),
    path('dodaj/', add_sale_view, name='add_sale'),
    path('<int:pk>/edytuj/', edit_sale_view, name='edit_sale'),
    path('<int:pk>/usun/', delete_sale_view, name='delete_sale'),
]
