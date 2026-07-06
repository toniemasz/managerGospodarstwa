import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
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
    recipe_version_item_formset_factory,
)
from common.date_range import PERIOD_OPTIONS, parse_date_range
from common.filter_ui import filter_ui_state, parse_filter_date
from farms.services.current_farm import get_current_farm
from farms.services.audit_log_service import log_action
from feed.actions.deliveries import create_delivery, delete_delivery, update_delivery
from feed.actions.inventory import InventoryActions
from feed.actions.productions import (
    complete_production,
    delete_production_with_inventory,
    mark_stage_1_done,
    update_production,
)
from feed.models import InventoryMovementModel, RecipeVersionModel
from feed.actions.recipes import create_recipe, update_recipe
from feed.actions.recipe_versions import (
    RecipeVersionActions,
    recipe_version_items_from_formset,
)
from feed.selectors.inventory import (
    deliveries_for_farm,
    ingredients_for_farm,
    inventory_dashboard,
    inventory_movements,
    latest_delivery_prices_map,
)
from feed.selectors.productions import (
    default_production_quantity,
    production_details_for_stages,
    productions_for_farm,
)
from feed.selectors.recipes import (
    calculator_price_rows,
    recipe_costs,
    recipe_detail as recipe_detail_context,
    recipe_exists,
    recipe_version_for_farm_or_404,
    recipes_with_items,
)


logger = logging.getLogger(__name__)


# --- SKŁADNIKI ---
@login_required
def ingredient_list_view(request):
    farm = get_current_farm(request)
    ingredients = ingredients_for_farm(farm)
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
    movement_type = request.GET.get('movement_type', '')
    date_from = parse_filter_date(request.GET.get('date_from'))
    date_to = parse_filter_date(request.GET.get('date_to'))
    context = inventory_dashboard(farm)
    context['deliveries'] = deliveries_for_farm(farm)
    movements = inventory_movements(farm, movement_type=movement_type, date_from=date_from, date_to=date_to)
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
            delivery = create_delivery(form, farm=farm, user=request.user)
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
            delivery = update_delivery(form, farm=farm, user=request.user)
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
            delete_delivery(delivery, farm=farm)
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
    recipes = recipes_with_items(farm)
    costs = {cost.recipe_id: cost for cost in recipe_costs(farm)}
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
    context = recipe_detail_context(
        farm,
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
            recipe = create_recipe(form, formset, farm=farm, user=request.user)
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
            recipe, version_created = update_recipe(form, formset, farm=farm, user=request.user)
            log_action(farm=farm, user=request.user, action="UPDATE", obj=recipe)
            if version_created:
                messages.success(
                    request,
                    "Zapisano nową wersję receptury. Wcześniejsze śrutowania nie zostały zmienione.",
                )
            else:
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
def recipe_version_detail_view(request, pk, version_pk):
    farm = get_current_farm(request)
    version = recipe_version_for_farm_or_404(farm, pk, version_pk)
    productions = (
        ProductionModel.objects
        .filter(recipe_version=version, recipe__farm=farm)
        .order_by('-date', '-time', '-id')
    )
    return render(request, 'feed/recipe_version_detail.html', {
        'recipe': version.recipe,
        'version': version,
        'productions': productions[:50],
        'production_count': productions.count(),
        'completed_count': productions.filter(status=ProductionModel.Statuses.COMPLETED).count(),
    })


@login_required
def add_recipe_version_view(request, pk, version_pk):
    farm = get_current_farm(request)
    source_version = recipe_version_for_farm_or_404(farm, pk, version_pk)
    recipe = source_version.recipe
    initial_items = [
        {'ingredient': item.ingredient, 'percentage': item.percentage}
        for item in source_version.items.select_related('ingredient').order_by('ingredient__name', 'id')
    ]
    extra = max(len(initial_items), 1)
    VersionItemFormSet = recipe_version_item_formset_factory(extra=extra if request.method != 'POST' else 0)
    version = RecipeVersionModel(recipe=recipe)

    if request.method == 'POST':
        formset = VersionItemFormSet(request.POST, instance=version, form_kwargs={'farm': farm})
        if formset.is_valid():
            try:
                new_version = RecipeVersionActions(farm=farm, user=request.user).create_new_version(
                    recipe=recipe,
                    source_version=source_version,
                    items=recipe_version_items_from_formset(formset),
                    change_note=f"Nowa wersja na podstawie v{source_version.version_number}",
                )
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(
                    request,
                    f"Utworzono nową wersję v{new_version.version_number}. Wcześniejsze śrutowania nie zostały zmienione.",
                )
                return redirect('recipe_detail', pk=recipe.pk)
    else:
        formset = VersionItemFormSet(
            instance=version,
            initial=initial_items,
            form_kwargs={'farm': farm},
        )

    return render(request, 'feed/recipe_version_form.html', {
        'recipe': recipe,
        'version': None,
        'source_version': source_version,
        'formset': formset,
        'is_edit': False,
        'requires_confirmation': False,
        'assigned_production_count': 0,
        'completed_production_count': 0,
        'custom_recipe_count': 0,
    })


@login_required
def edit_recipe_version_view(request, pk, version_pk):
    farm = get_current_farm(request)
    version = recipe_version_for_farm_or_404(farm, pk, version_pk)
    assigned_productions = ProductionModel.objects.filter(recipe_version=version, recipe__farm=farm)
    assigned_production_count = assigned_productions.count()
    completed_production_count = assigned_productions.filter(status=ProductionModel.Statuses.COMPLETED).count()
    custom_recipe_count = assigned_productions.filter(
        status=ProductionModel.Statuses.COMPLETED,
        custom_recipe_data__isnull=False,
    ).count()
    VersionItemFormSet = recipe_version_item_formset_factory(extra=0)

    if request.method == 'POST':
        formset = VersionItemFormSet(request.POST, instance=version, form_kwargs={'farm': farm})
        if formset.is_valid():
            try:
                result = RecipeVersionActions(farm=farm, user=request.user).update_existing_version(
                    version=version,
                    items=recipe_version_items_from_formset(formset),
                    confirm_recalculate=request.POST.get('confirm_recalculate') == 'on',
                )
            except ValidationError as error:
                messages.error(request, error.messages[0])
            else:
                messages.success(
                    request,
                    (
                        f"Zapisano wersję v{version.version_number}. "
                        f"Przeliczono {result.completed_count} zakończonych śrutowań tej wersji."
                    ),
                )
                if result.custom_recipe_count:
                    messages.warning(
                        request,
                        "Część przeliczonych produkcji ma jednorazowe zmiany składu. Zostały zachowane i uwzględnione.",
                    )
                return redirect('recipe_detail', pk=version.recipe_id)
    else:
        formset = VersionItemFormSet(instance=version, form_kwargs={'farm': farm})

    return render(request, 'feed/recipe_version_form.html', {
        'recipe': version.recipe,
        'version': version,
        'source_version': None,
        'formset': formset,
        'is_edit': True,
        'requires_confirmation': assigned_production_count > 0,
        'assigned_production_count': assigned_production_count,
        'completed_production_count': completed_production_count,
        'custom_recipe_count': custom_recipe_count,
    })


@login_required
def feed_production_view(request):
    farm = get_current_farm(request)
    productions = productions_for_farm(farm)
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
    if request.method == 'POST':
        form = ProductionForm(request.POST, farm=farm)
        if form.is_valid():
            production = form.save()
            try:
                log_action(farm=farm, user=request.user, action="CREATE", obj=production)
            except Exception:
                logger.exception("Nie udało się zapisać wpisu historii dla śrutowania %s", production.pk)
            if request.POST.get('instant_complete') == 'on':
                force_inventory = request.POST.get('force_inventory') == 'on'

                try:
                    success, message = complete_production(
                        farm,
                        production.id,
                        skip_stages=True,
                        force_inventory=force_inventory,
                        user=request.user,
                    )
                except Exception:
                    logger.exception("Nie udało się automatycznie zatwierdzić śrutowania %s", production.pk)
                    success = False
                    message = "wystąpił błąd podczas automatycznego zatwierdzania"
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
            'quantity_kg': default_production_quantity(farm),
            'date': now.date(),
            'time': now.strftime('%H:%M')
        }
        selected_recipe = request.GET.get('recipe')
        if selected_recipe and recipe_exists(farm, selected_recipe):
            initial['recipe'] = selected_recipe
        form = ProductionForm(farm=farm, initial=initial)

    recipes = recipes_with_items(farm)
    return render(request, 'feed/production_form.html', {'form': form, 'recipes': recipes, 'is_edit': False})

@login_required
def edit_production_view(request, pk):
    farm = get_current_farm(request)
    production = get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)

    if request.method == 'POST':
        form = ProductionForm(request.POST, instance=production, farm=farm)
        if form.is_valid():
            try:
                production = update_production(form)
            except ValidationError as error:
                form.add_error(None, error.messages[0])
            else:
                log_action(farm=farm, user=request.user, action="UPDATE", obj=production)
                messages.success(request, "Zaktualizowano parametry śrutowania i przeliczono FIFO.")
                return redirect('feed_productions')
    else:
        form = ProductionForm(instance=production, farm=farm)

    recipes = recipes_with_items(farm)
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
        delete_production_with_inventory(farm, production)
        log_action(farm=farm, user=request.user, action="DELETE", model_label="feed.ProductionModel", object_id=object_id, object_repr=representation)
        messages.success(request, "Usunięto śrutowanie.")
    return redirect('feed_productions')


@login_required
def process_stage1_view(request, pk):
    farm = get_current_farm(request)
    get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        success, message = mark_stage_1_done(farm, pk)
        if success:
            log_action(farm=farm, user=request.user, action="PRODUCTION_STAGE_1", obj=ProductionModel.objects.get(pk=pk))
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    context = production_details_for_stages(farm, pk)
    return render(request, 'feed/stage1.html', context)


@login_required
def process_stage2_view(request, pk):
    farm = get_current_farm(request)
    get_object_or_404(ProductionModel, pk=pk, recipe__farm=farm)
    if request.method == 'POST':
        skip_stages = request.POST.get('skip_stages') == 'on'

        force_inventory = request.POST.get('force_inventory') == 'on'

        success, message = complete_production(
            farm,
            pk,
            skip_stages=skip_stages,
            force_inventory=force_inventory,
            user=request.user,
        )
        if success:
            log_action(farm=farm, user=request.user, action="PRODUCTION_COMPLETED", obj=ProductionModel.objects.get(pk=pk), metadata={"forced": force_inventory})
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    context = production_details_for_stages(farm, pk)
    return render(request, 'feed/stage2.html', context)

@login_required
def feed_calculator_view(request):
    farm = get_current_farm(request)
    ingredients = list(ingredients_for_farm(farm))
    base_prices = latest_delivery_prices_map(farm)
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

    costs = recipe_costs(farm, price_overrides=overrides)
    ingredient_prices = calculator_price_rows(farm, overrides=overrides)
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
    farm = get_current_farm(request)
    context = inventory_dashboard(farm)
    return render(request, 'feed/full_inventory.html', context)


@login_required
def inventory_adjustment_view(request):
    farm = get_current_farm(request)
    if request.method == "POST":
        form = InventoryAdjustmentForm(request.POST, farm=farm)
        if form.is_valid():
            try:
                movement = InventoryActions(farm).adjust(
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
