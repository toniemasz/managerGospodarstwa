from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import ProtectedError
from django.utils import timezone
from decimal import Decimal, InvalidOperation

from .models import RecipeModel, ProductionModel, IngredientModel, DeliveryModel
from .forms import IngredientForm, RecipeForm, RecipeItemFormSet, DeliveryForm, ProductionForm
from .services.feed_management_service import FeedManagementService
from farms.services.farm_service import get_or_create_user_farm


def _current_farm(request):
    farm = getattr(request, 'farm', None)
    if farm is None and request.user.is_authenticated:
        farm = get_or_create_user_farm(request.user)
        request.farm = farm
    return farm


# --- SKŁADNIKI ---
@login_required
def ingredient_list_view(request):
    farm = _current_farm(request)
    ingredients = IngredientModel.objects.filter(farm=farm).order_by('name')
    return render(request, 'feed/ingredients.html', {'ingredients': ingredients})


@login_required
def add_ingredient_view(request):
    farm = _current_farm(request)
    if request.method == 'POST':
        form = IngredientForm(request.POST, farm=farm)
        if form.is_valid():
            ingredient = form.save(commit=False)
            ingredient.farm = farm
            ingredient.save()
            messages.success(request, "Składnik został dodany.")
            return redirect('ingredient_list')
    else:
        form = IngredientForm(farm=farm)
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Składnik', 'back_url': 'ingredient_list'})


@login_required
def edit_ingredient_view(request, pk):
    farm = _current_farm(request)
    ingredient = get_object_or_404(IngredientModel, pk=pk, farm=farm)
    if request.method == 'POST':
        form = IngredientForm(request.POST, instance=ingredient, farm=farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Zaktualizowano pomyślnie.")
            return redirect('ingredient_list')
    else:
        form = IngredientForm(instance=ingredient, farm=farm)
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': f'Edytuj Składnik: {ingredient.name}', 'back_url': 'ingredient_list'})


@login_required
def delete_ingredient_view(request, pk):
    farm = _current_farm(request)
    ingredient = get_object_or_404(IngredientModel, pk=pk, farm=farm)
    if request.method == 'POST':
        try:
            ingredient.delete()
            messages.success(request, "Składnik usunięty.")
        except ProtectedError:
            messages.error(request,
                           "Nie można usunąć składnika, ponieważ przypisane są do niego dostawy lub występuje w recepturze.")
    return redirect('ingredient_list')


# --- MAGAZYN / DOSTAWY ---
@login_required
def feed_inventory_view(request):
    farm = _current_farm(request)
    service = FeedManagementService(farm=farm)
    # Pobiera zaktualizowany słownik z serwisu (uwzględniający tylko zakończone produkcje)
    context = service.get_inventory_dashboard()
    # Dodajemy historię dostaw do widoku
    context['deliveries'] = DeliveryModel.objects.select_related('ingredient').filter(ingredient__farm=farm).order_by('-date', '-id')
    return render(request, 'feed/inventory.html', context)


@login_required
def add_delivery_view(request):
    farm = _current_farm(request)
    if request.method == 'POST':
        form = DeliveryForm(request.POST, farm=farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Dostawa została przyjęta na magazyn.")
            return redirect('feed_inventory')
    else:
        form = DeliveryForm(farm=farm)
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Dostawę', 'back_url': 'feed_inventory'})


@login_required
def edit_delivery_view(request, pk):
    farm = _current_farm(request)
    delivery = get_object_or_404(DeliveryModel, pk=pk, ingredient__farm=farm)
    if request.method == 'POST':
        form = DeliveryForm(request.POST, instance=delivery, farm=farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Dostawa zaktualizowana.")
            return redirect('feed_inventory')
    else:
        form = DeliveryForm(instance=delivery, farm=farm)
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Edytuj Dostawę', 'back_url': 'feed_inventory'})


@login_required
def delete_delivery_view(request, pk):
    farm = _current_farm(request)
    delivery = get_object_or_404(DeliveryModel, pk=pk, ingredient__farm=farm)
    if request.method == 'POST':
        delivery.delete()
        messages.success(request, "Dostawa usunięta z historii.")
    return redirect('feed_inventory')


# --- RECEPTURY ---
@login_required
def feed_recipes_view(request):
    farm = _current_farm(request)
    service = FeedManagementService(farm=farm)
    recipes = RecipeModel.objects.filter(farm=farm).prefetch_related('items__ingredient').order_by('name')
    costs = {cost.recipe_id: cost for cost in service.get_recipe_costs()}
    recipe_cards = [{'recipe': recipe, 'cost': costs.get(recipe.id)} for recipe in recipes]
    return render(request, 'feed/recipes.html', {'recipe_cards': recipe_cards})


@login_required
def recipe_detail_view(request, pk):
    farm = _current_farm(request)
    service = FeedManagementService(farm=farm)
    context = service.get_recipe_detail(pk)
    return render(request, 'feed/recipe_detail.html', context)


@login_required
def add_recipe_view(request):
    farm = _current_farm(request)
    recipe = RecipeModel(farm=farm)
    if request.method == 'POST':
        form = RecipeForm(request.POST, instance=recipe, farm=farm)
        recipe = form.instance
        recipe.farm = farm
        formset = RecipeItemFormSet(request.POST, instance=recipe, form_kwargs={'farm': farm})
        if form.is_valid() and formset.is_valid():
            recipe = form.save(commit=False)
            recipe.farm = farm
            recipe.save()
            formset.instance = recipe
            formset.save()
            messages.success(request, "Receptura została utworzona.")
            return redirect('feed_recipes')
    else:
        form = RecipeForm(instance=recipe, farm=farm)
        formset = RecipeItemFormSet(instance=recipe, form_kwargs={'farm': farm})
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': False})


@login_required
def edit_recipe_view(request, pk):
    farm = _current_farm(request)
    recipe = get_object_or_404(RecipeModel, pk=pk, farm=farm)
    if request.method == 'POST':
        form = RecipeForm(request.POST, instance=recipe, farm=farm)
        formset = RecipeItemFormSet(request.POST, instance=recipe, form_kwargs={'farm': farm})
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Receptura zaktualizowana.")
            return redirect('feed_recipes')
    else:
        form = RecipeForm(instance=recipe, farm=farm)
        formset = RecipeItemFormSet(instance=recipe, form_kwargs={'farm': farm})
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': True})


@login_required
def delete_recipe_view(request, pk):
    farm = _current_farm(request)
    recipe = get_object_or_404(RecipeModel, pk=pk, farm=farm)
    if request.method == 'POST':
        try:
            recipe.delete()
            messages.success(request, "Receptura usunięta.")
        except ProtectedError:
            messages.error(request, "Nie można usunąć receptury, ponieważ zrealizowano z jej użyciem śrutowanie.")
    return redirect('feed_recipes')


@login_required
def feed_production_view(request):
    farm = _current_farm(request)
    # Sortujemy najpierw po dacie malejąco, a potem po godzinie malejąco
    productions = ProductionModel.objects.select_related('recipe').filter(recipe__farm=farm).order_by('-date', '-time', '-id')
    return render(request, 'feed/productions.html', {'productions': productions})


# 2. Zaktualizuj wartości początkowe w formularzu dodawania:
@login_required
def add_production_view(request):
    farm = _current_farm(request)
    if request.method == 'POST':
        form = ProductionForm(request.POST, farm=farm)
        if form.is_valid():
            production = form.save()
            if request.POST.get('instant_complete') == 'on':
                force_inventory = request.POST.get('force_inventory') == 'on'

                service = FeedManagementService(farm=farm)
                success, message = service.complete_production(production.id, skip_stages=True,
                                                               force_inventory=force_inventory)
                if success:
                    messages.success(request, "Śrutowanie zostało od razu zatwierdzone.")
                else:
                    messages.warning(request, f"Zapisano w kolejce, ale nie udało się zatwierdzić: {message}")
            else:
                messages.success(request, "Śrutowanie zostało dodane do kolejki.")
            return redirect('feed_productions')
    else:
        now = timezone.now()
        initial = {
            'quantity_kg': 2000,
            'date': now.date(),
            'time': now.strftime('%H:%M')
        }
        selected_recipe = request.GET.get('recipe')
        if selected_recipe and RecipeModel.objects.filter(pk=selected_recipe, farm=farm).exists():
            initial['recipe'] = selected_recipe
        form = ProductionForm(farm=farm, initial=initial)

    recipes = RecipeModel.objects.filter(farm=farm).prefetch_related('items__ingredient').order_by('name')
    return render(request, 'feed/production_form.html', {'form': form, 'recipes': recipes})

@login_required
def edit_production_view(request, pk):
    farm = _current_farm(request)
    production = get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)

    # Zabezpieczenie: Nie edytujemy śrutowania, które już zmieniło stan magazynu
    if production.status == ProductionModel.Statuses.COMPLETED:
        messages.error(request, "Nie można edytować zakończonego śrutowania.")
        return redirect('feed_productions')

    if request.method == 'POST':
        form = ProductionForm(request.POST, instance=production, farm=farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Zaktualizowano parametry śrutowania.")
            return redirect('feed_productions')
    else:
        form = ProductionForm(instance=production, farm=farm)

    recipes = RecipeModel.objects.filter(farm=farm).prefetch_related('items__ingredient').order_by('name')
    return render(request, 'feed/production_form.html', {'form': form, 'recipes': recipes, 'is_edit': True})


@login_required
def delete_production_view(request, pk):
    farm = _current_farm(request)
    production = get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        # Zabezpieczenie integralności magazynu
        if production.status == ProductionModel.Statuses.COMPLETED:
            messages.error(request,
                           "Zakończone śrutowanie odjęło już towar z magazynu. Operacja usunięcia zablokowana.")
        else:
            production.delete()
            messages.success(request, "Usunięto planowane śrutowanie.")
    return redirect('feed_productions')


@login_required
def process_stage1_view(request, pk):
    farm = _current_farm(request)
    get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        service = FeedManagementService(farm=farm)
        success, message = service.process_production_stage_1(pk)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    service = FeedManagementService(farm=farm)
    context = service.get_production_details_for_stages(pk)
    return render(request, 'feed/stage1.html', context)


@login_required
def process_stage2_view(request, pk):
    farm = _current_farm(request)
    get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        service = FeedManagementService(farm=farm)
        skip_stages = request.POST.get('skip_stages') == 'on'

        force_inventory = request.POST.get('force_inventory') == 'on'

        success, message = service.complete_production(pk, skip_stages=skip_stages, force_inventory=force_inventory)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    service = FeedManagementService(farm=farm)
    context = service.get_production_details_for_stages(pk)
    return render(request, 'feed/stage2.html', context)

@login_required
def feed_calculator_view(request):
    farm = _current_farm(request)
    service = FeedManagementService(farm=farm)

    overrides = {}
    if request.method == 'POST':
        overrides = _parse_calculator_overrides(request.POST)
        messages.success(request, "Przeliczono koszt paszy dla podanych cen.")

    costs = service.get_recipe_costs(price_overrides=overrides)
    ingredient_prices = service.get_calculator_price_rows(overrides=overrides)

    return render(request, 'feed/calculator.html', {
        'costs': costs,
        'ingredient_prices': ingredient_prices,
    })


@login_required
def feed_full_inventory_view(request):
    """Widok wyświetlający pełny stan każdego surowca na magazynie."""
    farm = _current_farm(request)
    service = FeedManagementService(farm=farm)
    context = service.get_inventory_dashboard()
    return render(request, 'feed/full_inventory.html', context)


def _parse_calculator_overrides(post_data) -> dict[int, Decimal]:
    overrides = {}
    for key, value in post_data.items():
        if not key.startswith('price_'):
            continue
        ingredient_id = key.removeprefix('price_')
        if not ingredient_id.isdigit():
            continue
        normalized = (value or '0').replace(',', '.').strip()
        try:
            price = Decimal(normalized or '0')
        except InvalidOperation:
            price = Decimal('0.00')
        overrides[int(ingredient_id)] = price
    return overrides
