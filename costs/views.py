from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from costs.forms import CostCategoryForm, CostFilterForm, CostForm
from costs.models import CostCategoryModel, CostModel
from costs.services import CostService
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
    context = {
        "costs": costs,
        "summary": service.summarize(costs),
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
            saved = form.save(commit=False)
            saved.farm = farm
            if not saved.created_by_id:
                saved.created_by = request.user
            saved.full_clean()
            saved.save()
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
    return _cost_form_view(request, cost=get_object_or_404(CostModel, pk=pk, farm=farm), is_edit=True)


@login_required
def delete_cost_view(request, pk):
    farm = get_current_farm(request)
    cost = get_object_or_404(CostModel, pk=pk, farm=farm)
    if request.method == "POST":
        representation, object_id = str(cost), cost.pk
        cost.delete()
        log_action(farm=farm, user=request.user, action="DELETE", model_label="costs.CostModel", object_id=object_id, object_repr=representation)
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
            saved = form.save(commit=False)
            saved.farm = farm
            saved.save()
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
        category.is_active = False
        category.save(update_fields=("is_active", "updated_at"))
        log_action(farm=farm, user=request.user, action="DEACTIVATE", obj=category)
        messages.success(request, "Kategoria została dezaktywowana.")
    return redirect("cost_categories")
