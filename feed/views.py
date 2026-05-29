import logging
import traceback
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import RecipeModel, ProductionModel
from .forms import IngredientForm, RecipeForm, RecipeItemFormSet, DeliveryForm, ProductionForm, PriceConfigForm
from .application.services import FeedManagementService

logger = logging.getLogger(__name__)


@login_required
def feed_inventory_view(request):
    service = FeedManagementService()
    context = service.get_inventory_dashboard()
    return render(request, 'feed/inventory.html', context)


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

    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset})


@login_required
def feed_production_view(request):
    productions = ProductionModel.objects.select_related('recipe').order_by('-date')
    return render(request, 'feed/productions.html', {'productions': productions})


@login_required
def add_production_view(request):
    if request.method == 'POST':
        form = ProductionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('feed_productions')
    else:
        form = ProductionForm(initial={'quantity_kg': 2000})  # Domyślnie 2 tony
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Zarejestruj Śrutowanie', 'back_url': 'feed_productions'})


@login_required
def add_delivery_view(request):
    if request.method == 'POST':
        form = DeliveryForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('feed_inventory')
    else:
        form = DeliveryForm()
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Dostawę', 'back_url': 'feed_inventory'})


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
