from django.urls import path
from . import views

urlpatterns = [
    path('magazyn/', views.feed_inventory_view, name='feed_inventory'),
    path('magazyn/dostawa/', views.add_delivery_view, name='add_delivery'),

    path('receptury/', views.feed_recipes_view, name='feed_recipes'),
    path('receptury/dodaj/', views.add_recipe_view, name='add_recipe'),

    path('srutowanie/', views.feed_production_view, name='feed_productions'),
    path('srutowanie/dodaj/', views.add_production_view, name='add_production'),

    path('kalkulator/', views.feed_calculator_view, name='feed_calculator'),
]