import logging
import traceback
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import ProtectedError

from .models import RecipeModel, ProductionModel, IngredientModel, DeliveryModel
from .forms import IngredientForm, RecipeForm, RecipeItemFormSet, DeliveryForm, ProductionForm, PriceConfigForm
from .application.services import FeedManagementService

logger = logging.getLogger(__name__)

# --- SKŁADNIKI ---
@login_required
def ingredient_list_view(request):
    ingredients = IngredientModel.objects.all().order_by('name')
    return render(request, 'feed/ingredients.html', {'ingredients': ingredients})

@login_required
def add_ingredient_view(request):
    if request.method == 'POST':
        form = IngredientForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Składnik został dodany.")
            return redirect('ingredient_list')
    else:
        form = IngredientForm()
    return render(request, 'feed/form_generic.html', {'form': form, 'title': 'Dodaj Składnik', 'back_url': 'ingredient_list'})

@login_required
def edit_ingredient_view(request, pk):
    ingredient = get_object_or_404(IngredientModel, pk=pk)
    if request.method == 'POST':
        form = IngredientForm(request.POST, instance=ingredient)
        if form.is_valid():
            form.save()
            messages.success(request, "Zaktualizowano pomyślnie.")
            return redirect('ingredient_list')
    else:
        form = IngredientForm(instance=ingredient)
    return render(request, 'feed/form_generic.html', {'form': form, 'title': f'Edytuj Składnik: {ingredient.name}', 'back_url': 'ingredient_list'})

@login_required
def delete_ingredient_view(request, pk):
    ingredient = get_object_or_404(IngredientModel, pk=pk)
    if request.method == 'POST':
        try:
            ingredient.delete()
            messages.success(request, "Składnik usunięty.")
        except ProtectedError:
            messages.error(request, "Nie można usunąć składnika, ponieważ przypisane są do niego dostawy lub występuje w recepturze.")
    return redirect('ingredient_list')

# --- MAGAZYN / DOSTAWY ---
@login_required
def feed_inventory_view(request):
    service = FeedManagementService()
    context = service.get_inventory_dashboard()
    # Dodajemy historię dostaw do widoku
    context['deliveries'] = DeliveryModel.objects.select_related('ingredient').order_by('-date', '-id')
    return render(request, 'feed/inventory.html', context)

@login_required
def add_delivery_view(request):
    if request.method == 'POST':
        form = DeliveryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('feed_inventory')
    else:
        form = DeliveryForm()
    return render(request, 'feed/form_generic.html', {'form': form, 'title': 'Dodaj Dostawę', 'back_url': 'feed_inventory'})

@login_required
def edit_delivery_view(request, pk):
    delivery = get_object_or_404(DeliveryModel, pk=pk)
    if request.method == 'POST':
        form = DeliveryForm(request.POST, instance=delivery)
        if form.is_valid():
            form.save()
            return redirect('feed_inventory')
    else:
        form = DeliveryForm(instance=delivery)
    return render(request, 'feed/form_generic.html', {'form': form, 'title': 'Edytuj Dostawę', 'back_url': 'feed_inventory'})

@login_required
def delete_delivery_view(request, pk):
    delivery = get_object_or_404(DeliveryModel, pk=pk)
    if request.method == 'POST':
        delivery.delete()
    return redirect('feed_inventory')

# --- RECEPTURY ---
@login_required
def feed_recipes_view(request):
    recipes = RecipeModel.objects.prefetch_related('items__ingredient').all()
    return render(request, 'feed/recipes.html', {'recipes': recipes})

@login_required
def add_recipe_view(request):
    if request.method == 'POST':
        form = RecipeForm(request.POST)
        if form.is_valid():
            recipe = form.save()
            formset = RecipeItemFormSet(request.POST, instance=recipe)
            if formset.is_valid():
                formset.save()
                return redirect('feed_recipes')
    else:
        form = RecipeForm()
        formset = RecipeItemFormSet()
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': False})

@login_required
def edit_recipe_view(request, pk):
    recipe = get_object_or_404(RecipeModel, pk=pk)
    if request.method == 'POST':
        form = RecipeForm(request.POST, instance=recipe)
        formset = RecipeItemFormSet(request.POST, instance=recipe)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect('feed_recipes')
    else:
        form = RecipeForm(instance=recipe)
        formset = RecipeItemFormSet(instance=recipe)
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': True})

@login_required
def delete_recipe_view(request, pk):
    recipe = get_object_or_404(RecipeModel, pk=pk)
    if request.method == 'POST':
        try:
            recipe.delete()
        except ProtectedError:
            messages.error(request, "Nie można usunąć receptury, ponieważ zrealizowano z jej użyciem śrutowanie.")
    return redirect('feed_recipes')

# --- ŚRUTOWANIE (PRODUKCJA) ---
@login_required
def feed_production_view(request):
    productions = ProductionModel.objects.select_related('recipe').order_by('-date', '-id')
    return render(request, 'feed/productions.html', {'productions': productions})

@login_required
def add_production_view(request):
    if request.method == 'POST':
        form = ProductionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('feed_productions')
    else:
        form = ProductionForm(initial={'quantity_kg': 2000})
    return render(request, 'feed/form_generic.html', {'form': form, 'title': 'Zarejestruj Śrutowanie', 'back_url': 'feed_productions'})

@login_required
def edit_production_view(request, pk):
    production = get_object_or_404(ProductionModel, pk=pk)
    if request.method == 'POST':
        form = ProductionForm(request.POST, instance=production)
        if form.is_valid():
            form.save()
            return redirect('feed_productions')
    else:
        form = ProductionForm(instance=production)
    return render(request, 'feed/form_generic.html', {'form': form, 'title': 'Edytuj Śrutowanie', 'back_url': 'feed_productions'})

@login_required
def delete_production_view(request, pk):
    production = get_object_or_404(ProductionModel, pk=pk)
    if request.method == 'POST':
        production.delete()
    return redirect('feed_productions')

# --- KALKULATOR ---
@login_required
def feed_calculator_view(request):
    service = FeedManagementService()
    costs = service.get_calculator_data()

    if request.method == 'POST':
        form = PriceConfigForm(request.POST)
        if form.is_valid():
            ing = form.cleaned_data['ingredient']
            price = form.cleaned_data['price_per_kg']
            from .models import IngredientPriceConfigModel
            IngredientPriceConfigModel.objects.update_or_create(ingredient=ing, defaults={'price_per_kg': price})
            return redirect('feed_calculator')
    else:
        form = PriceConfigForm()

    return render(request, 'feed/calculator.html', {'costs': costs, 'form': form})