from django.urls import path

from costs import views


urlpatterns = [
    path("", views.cost_list_view, name="cost_list"),
    path("dodaj/", views.add_cost_view, name="add_cost"),
    path("<int:pk>/edytuj/", views.edit_cost_view, name="edit_cost"),
    path("<int:pk>/usun/", views.delete_cost_view, name="delete_cost"),
    path("kategorie/", views.cost_categories_view, name="cost_categories"),
    path("kategorie/dodaj/", views.add_cost_category_view, name="add_cost_category"),
    path("kategorie/<int:pk>/edytuj/", views.edit_cost_category_view, name="edit_cost_category"),
    path("kategorie/<int:pk>/dezaktywuj/", views.deactivate_cost_category_view, name="deactivate_cost_category"),
]
