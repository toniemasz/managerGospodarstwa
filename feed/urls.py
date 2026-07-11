# feed/urls.py
from django.urls import path
from . import finished_feed_views, production_views, views

urlpatterns = [
    # Składniki
    path('skladniki/', views.ingredient_list_view, name='ingredient_list'),
    path('skladniki/dodaj/', views.add_ingredient_view, name='add_ingredient'),
    path('skladniki/<int:pk>/edytuj/', views.edit_ingredient_view, name='edit_ingredient'),
    path('skladniki/<int:pk>/usun/', views.delete_ingredient_view, name='delete_ingredient'),

    # Magazyn i Dostawy
    path('magazyn/', views.feed_inventory_view, name='feed_inventory'),
    path('magazyn/dostawa/dodaj/', views.add_delivery_view, name='add_delivery'),
    path('magazyn/dostawa/<int:pk>/edytuj/', views.edit_delivery_view, name='edit_delivery'),
    path('magazyn/dostawa/<int:pk>/usun/', views.delete_delivery_view, name='delete_delivery'),
    path('magazyn/pelny/', views.feed_full_inventory_view, name='feed_full_inventory'),
    path('magazyn/korekta/', views.inventory_adjustment_view, name='inventory_adjustment'),
    path('magazyn/gotowe-pasze/', finished_feed_views.finished_feed_inventory_view, name='finished_feed_inventory'),
    path('magazyn/gotowe-pasze/zakup/', finished_feed_views.purchase_ready_feed_view, name='purchase_ready_feed'),
    path('magazyn/podania/', finished_feed_views.feed_servings_view, name='feed_servings'),
    path('magazyn/podania/dodaj/', finished_feed_views.create_feed_serving_view, name='create_feed_serving'),
    path('magazyn/podania/<int:pk>/usun/', finished_feed_views.delete_feed_serving_view, name='delete_feed_serving'),
    # Receptury
    path('receptury/', views.feed_recipes_view, name='feed_recipes'),
    path('receptury/dodaj/', views.add_recipe_view, name='add_recipe'),
    path('receptury/<int:pk>/', views.recipe_detail_view, name='recipe_detail'),
    path('receptury/<int:pk>/edytuj/', views.edit_recipe_view, name='edit_recipe'),
    path('receptury/<int:pk>/wersje/<int:version_pk>/', views.recipe_version_detail_view, name='recipe_version_detail'),
    path('receptury/<int:pk>/wersje/<int:version_pk>/edytuj/', views.edit_recipe_version_view, name='edit_recipe_version'),
    path('receptury/<int:pk>/wersje/<int:version_pk>/nowa/', views.add_recipe_version_view, name='add_recipe_version'),
    path('receptury/<int:pk>/usun/', views.delete_recipe_view, name='delete_recipe'),

    # Śrutowanie (Produkcja) - Kolejka główna
    path('srutowanie/', views.feed_production_view, name='feed_productions'),
    path('srutowanie/dodaj/', views.add_production_view, name='add_production'),
    path('srutowanie/zakoncz-zaznaczone/', production_views.bulk_complete_productions_view, name='bulk_complete_productions'),
    path('srutowanie/<int:pk>/edytuj/', views.edit_production_view, name='edit_production'),
    path('srutowanie/<int:pk>/usun/', views.delete_production_view, name='delete_production'),

    # Etapy śrutowania
    path('srutowanie/<int:pk>/etap1/', production_views.process_stage1_view, name='process_stage1'),
    path('srutowanie/<int:pk>/etap2/', production_views.process_stage2_view, name='process_stage2'),

    # Kalkulator
    path('kalkulator/', views.feed_calculator_view, name='feed_calculator'),
]
