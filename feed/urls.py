from django.urls import path
from . import views

urlpatterns = [
    # Składniki (NOWE)
    path('skladniki/', views.ingredient_list_view, name='ingredient_list'),
    path('skladniki/dodaj/', views.add_ingredient_view, name='add_ingredient'),
    path('skladniki/<int:pk>/edytuj/', views.edit_ingredient_view, name='edit_ingredient'),
    path('skladniki/<int:pk>/usun/', views.delete_ingredient_view, name='delete_ingredient'),

    # Magazyn i Dostawy
    path('magazyn/', views.feed_inventory_view, name='feed_inventory'),
    path('magazyn/dostawa/dodaj/', views.add_delivery_view, name='add_delivery'),
    path('magazyn/dostawa/<int:pk>/edytuj/', views.edit_delivery_view, name='edit_delivery'),
    path('magazyn/dostawa/<int:pk>/usun/', views.delete_delivery_view, name='delete_delivery'),

    # Receptury
    path('receptury/', views.feed_recipes_view, name='feed_recipes'),
    path('receptury/dodaj/', views.add_recipe_view, name='add_recipe'),
    path('receptury/<int:pk>/edytuj/', views.edit_recipe_view, name='edit_recipe'),
    path('receptury/<int:pk>/usun/', views.delete_recipe_view, name='delete_recipe'),

    # Śrutowanie (Produkcja)
    path('srutowanie/', views.feed_production_view, name='feed_productions'),
    path('srutowanie/dodaj/', views.add_production_view, name='add_production'),
    path('srutowanie/<int:pk>/edytuj/', views.edit_production_view, name='edit_production'),
    path('srutowanie/<int:pk>/usun/', views.delete_production_view, name='delete_production'),

    # Kalkulator
    path('kalkulator/', views.feed_calculator_view, name='feed_calculator'),
]