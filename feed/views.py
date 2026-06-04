# feed/views.py - REFACTORED VERSION
import logging
import traceback
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import ProtectedError
from django.utils import timezone
from django.urls import reverse_lazy

from .models import RecipeModel, ProductionModel, IngredientModel, DeliveryModel, IngredientPriceConfigModel
from .forms import IngredientForm, RecipeForm, RecipeItemFormSet, DeliveryForm, ProductionForm, PriceConfigForm
from .application.services import FeedManagementService

logger = logging.getLogger(__name__)


# ============================================================================
# MIXIN: Generic Delete View with ProtectedError Handling
# ============================================================================
class GenericDeleteMixin(LoginRequiredMixin, DeleteView):
    """
    Mixin to handle deletion of objects with ProtectedError handling.
    Subclasses should define: model, template_name, success_url
    Optional: success_message, error_message, protected_error_message
    """
    success_message = "Element został usunięty."
    error_message = "Nie można usunąć elementu ze względu na powiązania."
    
    def delete(self, request, *args, **kwargs):
        try:
            return super().delete(request, *args, **kwargs)
        except ProtectedError:
            messages.error(request, self.get_protected_error_message())
            return redirect(self.get_success_url())

    def get_success_message(self):
        return self.success_message

    def get_protected_error_message(self):
        return self.error_message


# ============================================================================
# MIXIN: Generic Update View
# ============================================================================
class GenericUpdateMixin(LoginRequiredMixin, UpdateView):
    """
    Mixin for updating objects with success message.
    Subclasses should define: model, form_class, template_name, success_url
    """
    success_message = "Element został zaktualizowany."

    def form_valid(self, form):
        messages.success(self.request, self.get_success_message())
        return super().form_valid(form)

    def get_success_message(self):
        return self.success_message


# ============================================================================
# SKŁADNIKI - Ingredients
# ============================================================================

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
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Składnik', 'back_url': 'ingredient_list'})


class IngredientUpdateView(GenericUpdateMixin):
    model = IngredientModel
    form_class = IngredientForm
    template_name = 'feed/form_generic.html'
    success_url = reverse_lazy('ingredient_list')
    success_message = "Składnik został zaktualizowany."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edytuj Składnik: {self.object.name}'
        context['back_url'] = 'ingredient_list'
        return context


class IngredientDeleteView(GenericDeleteMixin):
    model = IngredientModel
    template_name = 'feed/confirm_delete.html'
    success_url = reverse_lazy('ingredient_list')
    success_message = "Składnik usunięty."
    protected_error_message = "Nie można usunąć składnika, ponieważ przypisane są do niego dostawy lub występuje w recepturze."

    def get_protected_error_message(self):
        return self.protected_error_message


# Keep function-based views for backward compatibility
@login_required
def edit_ingredient_view(request, pk):
    return IngredientUpdateView.as_view()(request, pk=pk)


@login_required
def delete_ingredient_view(request, pk):
    return IngredientDeleteView.as_view()(request, pk=pk)


# ============================================================================
# MAGAZYN / DOSTAWY - Deliveries
# ============================================================================

@login_required
def feed_inventory_view(request):
    service = FeedManagementService()
    context = service.get_inventory_dashboard()
    context['deliveries'] = DeliveryModel.objects.select_related('ingredient').order_by('-date', '-id')
    return render(request, 'feed/inventory.html', context)


@login_required
def add_delivery_view(request):
    if request.method == 'POST':
        form = DeliveryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Dostawa została przyjęta na magazyn.")
            return redirect('feed_inventory')
    else:
        form = DeliveryForm()
    return render(request, 'feed/form_generic.html',
                  {'form': form, 'title': 'Dodaj Dostawę', 'back_url': 'feed_inventory'})


class DeliveryUpdateView(GenericUpdateMixin):
    model = DeliveryModel
    form_class = DeliveryForm
    template_name = 'feed/form_generic.html'
    success_url = reverse_lazy('feed_inventory')
    success_message = "Dostawa zaktualizowana."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edytuj Dostawę'
        context['back_url'] = 'feed_inventory'
        return context


class DeliveryDeleteView(GenericDeleteMixin):
    model = DeliveryModel
    template_name = 'feed/confirm_delete.html'
    success_url = reverse_lazy('feed_inventory')
    success_message = "Dostawa usunięta z historii."


@login_required
def edit_delivery_view(request, pk):
    return DeliveryUpdateView.as_view()(request, pk=pk)


@login_required
def delete_delivery_view(request, pk):
    return DeliveryDeleteView.as_view()(request, pk=pk)


# ============================================================================
# RECEPTURY - Recipes
# ============================================================================

@login_required
def feed_recipes_view(request):
    recipes = RecipeModel.objects.prefetch_related('items__ingredient').all()
    return render(request, 'feed/recipes.html', {'recipes': recipes})


@login_required
def add_recipe_view(request):
    if request.method == 'POST':
        # Inicjalizujemy oba formularze od razu, by zawsze istniały
        form = RecipeForm(request.POST)
        formset = RecipeItemFormSet(request.POST)

        # Sprawdzamy poprawność OBU formularzy jednocześnie
        if form.is_valid() and formset.is_valid():
            recipe = form.save()
            # Przypinamy nowo utworzoną recepturę do formsetu i zapisujemy go
            formset.instance = recipe
            formset.save()

            messages.success(request, "Receptura została utworzona.")
            return redirect('feed_recipes')
    else:
        form = RecipeForm()
        formset = RecipeItemFormSet()

    return render(request, 'feed/add_recipe.html', {
        'form': form,
        'formset': formset,
        'is_edit': False
    })

@login_required
def edit_recipe_view(request, pk):
    recipe = get_object_or_404(RecipeModel, pk=pk)
    if request.method == 'POST':
        form = RecipeForm(request.POST, instance=recipe)
        formset = RecipeItemFormSet(request.POST, instance=recipe)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, "Receptura zaktualizowana.")
            return redirect('feed_recipes')
    else:
        form = RecipeForm(instance=recipe)
        formset = RecipeItemFormSet(instance=recipe)
    return render(request, 'feed/add_recipe.html', {'form': form, 'formset': formset, 'is_edit': True})


class RecipeDeleteView(GenericDeleteMixin):
    model = RecipeModel
    template_name = 'feed/confirm_delete.html'
    success_url = reverse_lazy('feed_recipes')
    success_message = "Receptura usunięta."
    protected_error_message = "Nie można usunąć receptury, ponieważ zrealizowano z jej użyciem śrutowanie."


@login_required
def delete_recipe_view(request, pk):
    return RecipeDeleteView.as_view()(request, pk=pk)


# ============================================================================
# PRODUKCJE / ŚRUTOWANIA - Productions
# ============================================================================

@login_required
def feed_production_view(request):
    productions = ProductionModel.objects.select_related('recipe').order_by('-date', '-time', '-id')
    return render(request, 'feed/productions.html', {'productions': productions})


@login_required
def add_production_view(request):
    if request.method == 'POST':
        form = ProductionForm(request.POST)
        if form.is_valid():
            production = form.save()
            if request.POST.get('instant_complete') == 'on':
                force_inventory = request.POST.get('force_inventory') == 'on'
                service = FeedManagementService()
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
        form = ProductionForm(initial={
            'quantity_kg': 2000,
            'date': now.date(),
            'time': now.strftime('%H:%M')
        })

    recipes = RecipeModel.objects.prefetch_related('items__ingredient').all()
    return render(request, 'feed/production_form.html', {'form': form, 'recipes': recipes})


@login_required
def edit_production_view(request, pk):
    production = get_object_or_404(ProductionModel, pk=pk)

    if production.status == ProductionModel.Statuses.COMPLETED:
        messages.error(request, "Nie można edytować zakończonego śrutowania.")
        return redirect('feed_productions')

    if request.method == 'POST':
        form = ProductionForm(request.POST, instance=production)
        if form.is_valid():
            form.save()
            messages.success(request, "Zaktualizowano parametry śrutowania.")
            return redirect('feed_productions')
    else:
        form = ProductionForm(instance=production)

    recipes = RecipeModel.objects.prefetch_related('items__ingredient').all()
    return render(request, 'feed/production_form.html', {'form': form, 'recipes': recipes, 'is_edit': True})


@login_required
def delete_production_view(request, pk):
    production = get_object_or_404(ProductionModel, pk=pk)
    if request.method == 'POST':
        if production.status == ProductionModel.Statuses.COMPLETED:
            messages.error(request, "Zakończone śrutowanie odjęło już towar z magazynu. Operacja usunięcia zablokowana.")
        else:
            production.delete()
            messages.success(request, "Usunięto planowane śrutowanie z kolejki.")
    return redirect('feed_productions')


@login_required
def process_stage1_view(request, pk):
    if request.method == 'POST':
        service = FeedManagementService()
        success, message = service.process_production_stage_1(pk)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    service = FeedManagementService()
    context = service.get_production_details_for_stages(pk)
    return render(request, 'feed/stage1.html', context)


@login_required
def process_stage2_view(request, pk):
    if request.method == 'POST':
        service = FeedManagementService()
        skip_stages = request.POST.get('skip_stages') == 'on'
        force_inventory = request.POST.get('force_inventory') == 'on'

        success, message = service.complete_production(pk, skip_stages=skip_stages, force_inventory=force_inventory)
        if success:
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect('feed_productions')

    service = FeedManagementService()
    context = service.get_production_details_for_stages(pk)
    return render(request, 'feed/stage2.html', context)


@login_required
def feed_calculator_view(request):
    service = FeedManagementService()
    costs = service.get_calculator_data()

    if request.method == 'POST':
        form = PriceConfigForm(request.POST)
        if form.is_valid():
            ing = form.cleaned_data['ingredient']
            price = form.cleaned_data['price_per_kg']
            IngredientPriceConfigModel.objects.update_or_create(ingredient=ing, defaults={'price_per_kg': price})
            messages.success(request, "Zaktualizowano cenę domyślną.")
            return redirect('feed_calculator')
    else:
        form = PriceConfigForm()

    return render(request, 'feed/calculator.html', {'costs': costs, 'form': form})


@login_required
def feed_full_inventory_view(request):
    """Widok wyświetlający pełny stan każdego surowca na magazynie."""
    service = FeedManagementService()
    context = service.get_inventory_dashboard()
    return render(request, 'feed/full_inventory.html', context)
