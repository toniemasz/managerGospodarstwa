from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from costs.forms import CostCategoryForm, CostFilterForm, CostForm
from costs.models import CostCategoryModel, CostModel
from costs.services import CostService
from costs.actions import (
    CostCategoryNameConflictError,
    deactivate_cost_category,
    delete_manual_cost,
    save_cost_category,
    save_manual_cost,
)
from common.filter_ui import filter_ui_state
from farms.services.accounting_year import get_available_years
from farms.services.audit_log_service import log_action
from farms.services.current_farm import get_current_farm


@login_required
def cost_list_view(request):
    farm = get_current_farm(request)
    form = CostFilterForm(request.GET or None, farm=farm, initial={"year": timezone.localdate().year})
    filters = {"year": timezone.localdate().year}
    if form.is_valid():
        filters.update({key: value for key, value in form.cleaned_data.items() if value not in (None, "")})
    service = CostService(farm)
    costs = service.get_costs(**filters)
    grouped_history = service.grouped_history(costs)
    context = {
        "costs": grouped_history["costs"],
        "category_groups": grouped_history["category_groups"],
        "summary": grouped_history["summary"],
        "filter_form": form,
        "selected_year": filters.get("year"),
        "available_years": get_available_years(farm),
    }
    context.update(filter_ui_state(request.GET, {
        'year': 'Rok', 'date_from': 'Od', 'date_to': 'Do',
        'category': 'Kategoria', 'payment_status': 'Płatność',
    }))
    return render(request, "costs/cost_list.html", context)


def _cost_form_view(request, *, cost, is_edit):
    farm = get_current_farm(request)
    if request.method == "POST":
        form = CostForm(request.POST, instance=cost, farm=farm)
        if form.is_valid():
            saved = save_manual_cost(farm=farm, form=form, user=request.user)
            log_action(farm=farm, user=request.user, action="UPDATE" if is_edit else "CREATE", obj=saved)
            messages.success(request, "Koszt został zapisany.")
            return redirect("cost_list")
    else:
        form = CostForm(instance=cost, farm=farm, initial={"date": timezone.localdate()})
    return render(request, "costs/cost_form.html", {"form": form, "cost": cost, "is_edit": is_edit})


@login_required
def add_cost_view(request):
    return _cost_form_view(request, cost=CostModel(farm=get_current_farm(request)), is_edit=False)


@login_required
def edit_cost_view(request, pk):
    farm = get_current_farm(request)
    cost = get_object_or_404(CostModel, pk=pk, farm=farm)
    if cost.production_id:
        messages.error(request, "Koszt paszy jest wyliczany automatycznie z FIFO i nie można go edytować ręcznie.")
        return redirect("cost_list")
    return _cost_form_view(request, cost=cost, is_edit=True)


@login_required
@require_POST
def delete_cost_view(request, pk):
    farm = get_current_farm(request)
    cost = get_object_or_404(CostModel, pk=pk, farm=farm)
    if cost.production_id:
        messages.error(request, "Koszt paszy jest powiązany ze śrutowaniem i nie można go usunąć ręcznie.")
        return redirect("cost_list")
    deleted = delete_manual_cost(farm=farm, cost_id=cost.pk)
    log_action(farm=farm, user=request.user, action="DELETE", **deleted)
    messages.success(request, "Koszt został usunięty.")
    return redirect("cost_list")


@login_required
def cost_categories_view(request):
    farm = get_current_farm(request)
    return render(request, "costs/categories.html", {"categories": CostService(farm).categories()})


def _category_form_view(request, *, category, is_edit):
    farm = get_current_farm(request)
    if request.method == "POST":
        form = CostCategoryForm(request.POST, instance=category, farm=farm)
        if form.is_valid():
            try:
                saved = save_cost_category(farm=farm, form=form)
            except CostCategoryNameConflictError as error:
                form.add_error('name', error.messages[0])
            else:
                log_action(farm=farm, user=request.user, action="UPDATE" if is_edit else "CREATE", obj=saved)
                messages.success(request, "Kategoria kosztów została zapisana.")
                return redirect("cost_categories")
    else:
        form = CostCategoryForm(instance=category, farm=farm)
    return render(request, "costs/category_form.html", {"form": form, "category": category, "is_edit": is_edit})


@login_required
def add_cost_category_view(request):
    return _category_form_view(request, category=CostCategoryModel(farm=get_current_farm(request)), is_edit=False)


@login_required
def edit_cost_category_view(request, pk):
    farm = get_current_farm(request)
    return _category_form_view(request, category=get_object_or_404(CostCategoryModel, pk=pk, farm=farm), is_edit=True)


@login_required
def deactivate_cost_category_view(request, pk):
    farm = get_current_farm(request)
    category = get_object_or_404(CostCategoryModel, pk=pk, farm=farm)
    if request.method == "POST":
        category = deactivate_cost_category(farm=farm, category_id=category.pk)
        log_action(farm=farm, user=request.user, action="DEACTIVATE", obj=category)
        messages.success(request, "Kategoria została dezaktywowana.")
    return redirect("cost_categories")
