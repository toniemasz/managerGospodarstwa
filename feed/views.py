from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.utils import timezone

from .models import RecipeModel, ProductionModel, IngredientModel, DeliveryModel
from .forms import (
    CalculatorPriceForm,
    DeliveryForm,
    IngredientForm,
    InventoryAdjustmentForm,
    ProductionForm,
    RecipeForm,
    RecipeItemFormSet,
)
from .services.feed_management_service import FeedManagementService
from .services.feed_repository import FeedRepository
from farms.services.current_farm import get_current_farm
from farms.services.date_range import PERIOD_OPTIONS, parse_date_range
from farms.services.filter_ui import filter_ui_state, parse_filter_date
from farms.services.audit_log_service import log_action
from feed.services.inventory_service import InventoryMovementService
from feed.models import InventoryMovementModel


# --- SKŁADNIKI ---
@login_required
def ingredient_list_view(request):
    farm = get_current_farm(request)
    ingredients = FeedRepository(farm=farm).get_all_ingredients()
    return render(request, 'feed/ingredients.html', {'ingredients': ingredients})


@login_required
def add_ingredient_view(request):
    farm = get_current_farm(request)
    if request.method == 'POST':
        form = IngredientForm(request.POST, farm=farm)
        if form.is_valid():
            ingredient = form.save(commit=False)
            ingredient.farm = farm
            ingredient.save()
            log_action(farm=farm, user=request.user, action="CREATE", obj=ingredient)
            messages.success(request, "Składnik został dodany.")
            return redirect('ingredient_list')
    else:
        form = IngredientForm(farm=farm)
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Składnik', 'back_url': 'ingredient_list'})


@login_required
def edit_ingredient_view(request, pk):
    farm = get_current_farm(request)
    ingredient = get_object_or_404(IngredientModel, pk=pk, farm=farm)
    if request.method == 'POST':
        form = IngredientForm(request.POST, instance=ingredient, farm=farm)
        if form.is_valid():
            ingredient = form.save()
            log_action(farm=farm, user=request.user, action="UPDATE", obj=ingredient)
            messages.success(request, "Zaktualizowano pomyślnie.")
            return redirect('ingredient_list')
    else:
        form = IngredientForm(instance=ingredient, farm=farm)
    return render(request, 'feed/form_generic.html',
                  {
                      'form': form,
                      'title': f'Edytuj Składnik: {ingredient.name}',
                      'back_url': 'ingredient_list',
                      'delete_url': 'delete_ingredient',
                      'delete_id': ingredient.id,
                      'delete_label': 'Usuń składnik',
                      'delete_confirm': f"Czy na pewno usunąć składnik: {ingredient.name}?",
                  })


@login_required
def delete_ingredient_view(request, pk):
    farm = get_current_farm(request)
    ingredient = get_object_or_404(IngredientModel, pk=pk, farm=farm)
    if request.method == 'POST':
        try:
            representation = str(ingredient)
            object_id = ingredient.pk
            ingredient.delete()
            log_action(farm=farm, user=request.user, action="DELETE", model_label="feed.IngredientModel", object_id=object_id, object_repr=representation)
            messages.success(request, "Składnik usunięty.")
        except (ProtectedError, RestrictedError):
            messages.error(request,
                           "Nie można usunąć składnika, ponieważ przypisane są do niego dostawy lub występuje w recepturze.")
    return redirect('ingredient_list')


# --- MAGAZYN / DOSTAWY ---
@login_required
def feed_inventory_view(request):
    farm = get_current_farm(request)
    service = FeedManagementService(farm=farm)
    # Pobiera zaktualizowany słownik z serwisu (uwzględniający tylko zakończone produkcje)
    context = service.get_inventory_dashboard()
    # Dodajemy historię dostaw do widoku
    context['deliveries'] = service.repository.get_deliveries()
    movements = InventoryMovementModel.objects.filter(farm=farm).select_related('ingredient')
    movement_type = request.GET.get('movement_type', '')
    date_from = parse_filter_date(request.GET.get('date_from'))
    date_to = parse_filter_date(request.GET.get('date_to'))
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if date_from:
        movements = movements.filter(movement_date__gte=date_from)
    if date_to:
        movements = movements.filter(movement_date__lte=date_to)
    context['movements'] = movements[:50]
    context['movement_types'] = InventoryMovementModel.Types.choices
    context.update(filter_ui_state(request.GET, {'movement_type': 'Typ', 'date_from': 'Od', 'date_to': 'Do'}))
    return render(request, 'feed/inventory.html', context)


@login_required
def add_delivery_view(request):
    farm = get_current_farm(request)
    if request.method == 'POST':
        form = DeliveryForm(request.POST, farm=farm)
        if form.is_valid():
            delivery = form.save()
            InventoryMovementService(farm).sync_delivery(delivery, user=request.user)
            log_action(farm=farm, user=request.user, action="CREATE", obj=delivery)
            messages.success(request, "Dostawa została przyjęta na magazyn.")
            return redirect('feed_inventory')
    else:
        form = DeliveryForm(farm=farm)
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Dostawę', 'back_url': 'feed_inventory'})


@login_required
def edit_delivery_view(request, pk):
    farm = get_current_farm(request)
    delivery = get_object_or_404(DeliveryModel, pk=pk, ingredient__farm=farm)
    if request.method == 'POST':
        form = DeliveryForm(request.POST, instance=delivery, farm=farm)
        if form.is_valid():
            with transaction.atomic():
                delivery = form.save()
                InventoryMovementService(farm).sync_delivery(delivery, user=request.user)
                InventoryMovementService(farm).rebuild()
            log_action(farm=farm, user=request.user, action="UPDATE", obj=delivery)
            messages.success(request, "Dostawa zaktualizowana.")
            return redirect('feed_inventory')
    else:
        form = DeliveryForm(instance=delivery, farm=farm)
    return render(request, 'feed/form_generic.html',
                  {
                      'form': form,
                      'title': 'Edytuj Dostawę',
                      'back_url': 'feed_inventory',
                      'delete_url': 'delete_delivery',
                      'delete_id': delivery.id,
                      'delete_label': 'Usuń dostawę',
                      'delete_confirm': (
                          f"Usunięcie tej dostawy zmniejszy stan magazynowy składnika "
                          f"{delivery.ingredient.name} o {delivery.quantity_kg} kg. Kontynuować?"
                      ),
                  })


@login_required
def delete_delivery_view(request, pk):
    farm = get_current_farm(request)
    delivery = get_object_or_404(DeliveryModel, pk=pk, ingredient__farm=farm)
    if request.method == 'POST':
        representation = str(delivery)
        object_id = delivery.pk
        try:
            with transaction.atomic():
                InventoryMovementService(farm).remove_delivery(delivery)
                delivery.delete()
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            log_action(farm=farm, user=request.user, action="DELETE", model_label="feed.DeliveryModel", object_id=object_id, object_repr=representation)
            messages.success(request, "Dostawa usunięta z historii.")
    return redirect('feed_inventory')


# --- RECEPTURY ---
@login_required
def feed_recipes_view(request):
    farm = get_current_farm(request)
    service = FeedManagementService(farm=farm)
    recipes = service.repository.get_recipes_with_items()
    costs = {cost.recipe_id: cost for cost in service.get_recipe_costs()}
    recipe_cards = [{'recipe': recipe, 'cost': costs.get(recipe.id)} for recipe in recipes]
    return render(request, 'feed/recipes.html', {'recipe_cards': recipe_cards})


@login_required
def recipe_detail_view(request, pk):
    farm = get_current_farm(request)
    date_range = parse_date_range(request.GET, default_period='6m')
    try:
        production_year = int(request.GET.get('year') or timezone.localdate().year)
    except (TypeError, ValueError):
        production_year = timezone.localdate().year
    service = FeedManagementService(farm=farm)
    context = service.get_recipe_detail(
        pk,
        date_from=date_range.date_from,
        date_to=date_range.date_to,
        production_year=production_year,
    )
    context['date_filter'] = date_range
    context['period_options'] = PERIOD_OPTIONS
    context.update(filter_ui_state(request.GET, {
        'period': 'Okres', 'date_from': 'Od', 'date_to': 'Do',
    }))
    return render(request, 'feed/recipe_detail.html', context)


@login_required
def add_recipe_view(request):
    farm = get_current_farm(request)
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
            log_action(farm=farm, user=request.user, action="CREATE", obj=recipe)
            messages.success(request, "Receptura została utworzona.")
            return redirect('feed_recipes')
    else:
        form = RecipeForm(instance=recipe, farm=farm)
        formset = RecipeItemFormSet(instance=recipe, form_kwargs={'farm': farm})
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': False})


@login_required
def edit_recipe_view(request, pk):
    farm = get_current_farm(request)
    recipe = get_object_or_404(RecipeModel, pk=pk, farm=farm)
    if request.method == 'POST':
        form = RecipeForm(request.POST, instance=recipe, farm=farm)
        formset = RecipeItemFormSet(request.POST, instance=recipe, form_kwargs={'farm': farm})
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            log_action(farm=farm, user=request.user, action="UPDATE", obj=recipe)
            messages.success(request, "Receptura zaktualizowana.")
            return redirect('feed_recipes')
    else:
        form = RecipeForm(instance=recipe, farm=farm)
        formset = RecipeItemFormSet(instance=recipe, form_kwargs={'farm': farm})
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': True, 'recipe': recipe})


@login_required
def delete_recipe_view(request, pk):
    farm = get_current_farm(request)
    recipe = get_object_or_404(RecipeModel, pk=pk, farm=farm)
    if request.method == 'POST':
        try:
            representation = str(recipe)
            object_id = recipe.pk
            recipe.delete()
            log_action(farm=farm, user=request.user, action="DELETE", model_label="feed.RecipeModel", object_id=object_id, object_repr=representation)
            messages.success(request, "Receptura usunięta.")
        except (ProtectedError, RestrictedError):
            messages.error(request, "Nie można usunąć receptury, ponieważ zrealizowano z jej użyciem śrutowanie.")
    return redirect('feed_recipes')


@login_required
def feed_production_view(request):
    farm = get_current_farm(request)
    # Sortujemy najpierw po dacie malejąco, a potem po godzinie malejąco
    productions = FeedRepository(farm=farm).get_productions()
    status = request.GET.get('status', '')
    date_from = parse_filter_date(request.GET.get('date_from'))
    date_to = parse_filter_date(request.GET.get('date_to'))
    if status:
        productions = productions.filter(status=status)
    if date_from:
        productions = productions.filter(date__gte=date_from)
    if date_to:
        productions = productions.filter(date__lte=date_to)
    context = {'productions': productions, 'production_statuses': ProductionModel.Statuses.choices}
    context.update(filter_ui_state(request.GET, {'status': 'Status', 'date_from': 'Od', 'date_to': 'Do'}))
    return render(request, 'feed/productions.html', context)


@login_required
def add_production_view(request):
    farm = get_current_farm(request)
    service = FeedManagementService(farm=farm)
    if request.method == 'POST':
        form = ProductionForm(request.POST, farm=farm)
        if form.is_valid():
            production = form.save()
            log_action(farm=farm, user=request.user, action="CREATE", obj=production)
            if request.POST.get('instant_complete') == 'on':
                force_inventory = request.POST.get('force_inventory') == 'on'

                success, message = service.complete_production(production.id, skip_stages=True,
                                                               force_inventory=force_inventory, user=request.user)
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
            'quantity_kg': service.get_default_production_quantity(),
            'date': now.date(),
            'time': now.strftime('%H:%M')
        }
        selected_recipe = request.GET.get('recipe')
        if selected_recipe and service.repository.recipe_exists(selected_recipe):
            initial['recipe'] = selected_recipe
        form = ProductionForm(farm=farm, initial=initial)

    recipes = service.repository.get_recipes_with_items()
    return render(request, 'feed/production_form.html', {'form': form, 'recipes': recipes, 'is_edit': False})

@login_required
def edit_production_view(request, pk):
    farm = get_current_farm(request)
    production = get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)

    if request.method == 'POST':
        form = ProductionForm(request.POST, instance=production, farm=farm)
        if form.is_valid():
            try:
                with transaction.atomic():
                    production = form.save()
            except ValidationError as error:
                form.add_error(None, error.messages[0])
            else:
                log_action(farm=farm, user=request.user, action="UPDATE", obj=production)
                messages.success(request, "Zaktualizowano parametry śrutowania i przeliczono FIFO.")
                return redirect('feed_productions')
    else:
        form = ProductionForm(instance=production, farm=farm)

    recipes = FeedRepository(farm=farm).get_recipes_with_items()
    return render(request, 'feed/production_form.html', {
        'form': form,
        'recipes': recipes,
        'is_edit': True,
        'production': production,
    })


@login_required
def delete_production_view(request, pk):
    farm = get_current_farm(request)
    production = get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        representation = str(production)
        object_id = production.pk
        with transaction.atomic():
            InventoryMovementService(farm).release_production(production)
            production.delete()
        log_action(farm=farm, user=request.user, action="DELETE", model_label="feed.ProductionModel", object_id=object_id, object_repr=representation)
        messages.success(request, "Usunięto śrutowanie.")
    return redirect('feed_productions')


@login_required
def process_stage1_view(request, pk):
    farm = get_current_farm(request)
    get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        service = FeedManagementService(farm=farm)
        success, message = service.process_production_stage_1(pk)
        if success:
            log_action(farm=farm, user=request.user, action="PRODUCTION_STAGE_1", obj=ProductionModel.objects.get(pk=pk))
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    service = FeedManagementService(farm=farm)
    context = service.get_production_details_for_stages(pk)
    return render(request, 'feed/stage1.html', context)


@login_required
def process_stage2_view(request, pk):
    farm = get_current_farm(request)
    get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        service = FeedManagementService(farm=farm)
        skip_stages = request.POST.get('skip_stages') == 'on'

        force_inventory = request.POST.get('force_inventory') == 'on'

        success, message = service.complete_production(pk, skip_stages=skip_stages, force_inventory=force_inventory, user=request.user)
        if success:
            log_action(farm=farm, user=request.user, action="PRODUCTION_COMPLETED", obj=ProductionModel.objects.get(pk=pk), metadata={"forced": force_inventory})
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    service = FeedManagementService(farm=farm)
    context = service.get_production_details_for_stages(pk)
    return render(request, 'feed/stage2.html', context)

@login_required
def feed_calculator_view(request):
    farm = get_current_farm(request)
    service = FeedManagementService(farm=farm)
    ingredients = list(service.repository.get_all_ingredients())
    base_prices = service.repository.get_latest_delivery_prices_map()
    price_form = CalculatorPriceForm(
        request.POST or None,
        ingredients=ingredients,
        prices=base_prices,
    )

    overrides = {}
    if request.method == 'POST':
        if price_form.is_valid():
            overrides = price_form.price_overrides()
            messages.success(request, "Przeliczono koszt paszy dla podanych cen.")
        else:
            messages.error(request, "Nie przeliczono kosztu paszy. Popraw oznaczone ceny składników.")

    costs = service.get_recipe_costs(price_overrides=overrides)
    ingredient_prices = service.get_calculator_price_rows(overrides=overrides)
    for row in ingredient_prices:
        field_name = CalculatorPriceForm.field_name_for_ingredient(row['ingredient'].id)
        row['field'] = price_form[field_name]

    return render(request, 'feed/calculator.html', {
        'costs': costs,
        'ingredient_prices': ingredient_prices,
        'price_form': price_form,
    })


@login_required
def feed_full_inventory_view(request):
    """Widok wyświetlający pełny stan każdego surowca na magazynie."""
    farm = get_current_farm(request)
    service = FeedManagementService(farm=farm)
    context = service.get_inventory_dashboard()
    return render(request, 'feed/full_inventory.html', context)


@login_required
def inventory_adjustment_view(request):
    farm = get_current_farm(request)
    if request.method == "POST":
        form = InventoryAdjustmentForm(request.POST, farm=farm)
        if form.is_valid():
            try:
                movement = InventoryMovementService(farm).adjust(
                    **form.cleaned_data,
                    user=request.user,
                )
            except ValidationError as error:
                form.add_error(None, error.messages[0])
            else:
                log_action(farm=farm, user=request.user, action="INVENTORY_ADJUSTMENT", obj=movement)
                messages.success(request, "Korekta magazynowa została zapisana.")
                return redirect("feed_inventory")
    else:
        form = InventoryAdjustmentForm(farm=farm, initial={"movement_date": timezone.localdate()})
    return render(request, "feed/form_generic.html", {
        "form": form,
        "title": "Korekta stanu magazynowego",
        "back_url": "feed_inventory",
    })
