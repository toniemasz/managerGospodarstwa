from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from farms.services.audit_log_service import log_action
from farms.services.current_farm import get_current_farm
from feed.actions.productions import (
    bulk_complete_productions,
    complete_production,
    mark_stage_1_done,
)
from feed.models import ProductionModel
from feed.selectors.productions import production_details_for_stages, production_or_404
from feed.services.production_reversal import ProductionSettlementReversalWorkflow


def _checklist_is_complete(request, items) -> bool:
    expected_ids = {str(item["id"]) for item in items}
    confirmed_ids = set(request.POST.getlist("confirmed_ingredients"))
    return expected_ids == confirmed_ids


def _redirect_from_stage_1(request, production):
    if production.status == ProductionModel.Statuses.STAGE_1_DONE:
        messages.info(request, "Etap 1 został już zakończony. Przejdź do Etapu 2.")
        return redirect("process_stage2", pk=production.pk)
    if production.status == ProductionModel.Statuses.COMPLETED:
        messages.info(request, "To śrutowanie jest już zakończone.")
        return redirect("feed_productions")
    return None


@login_required
@require_http_methods(["GET", "POST"])
def process_stage1_view(request, pk):
    farm = get_current_farm(request)
    production = production_or_404(farm, pk)

    redirect_response = _redirect_from_stage_1(request, production)
    if redirect_response:
        return redirect_response

    context = production_details_for_stages(farm, pk)
    if request.method == "POST":
        if not _checklist_is_complete(request, context["stage1_items"]):
            messages.error(request, "Potwierdź pobranie wszystkich składników z silosów.")
            return render(request, "feed/stage1.html", context, status=400)
        success, message = mark_stage_1_done(farm, pk)
        if success:
            production.refresh_from_db()
            log_action(
                farm=farm,
                user=request.user,
                action="PRODUCTION_STAGE_1",
                obj=production,
            )
            messages.success(request, message)
            return redirect("process_stage2", pk=pk)
        messages.error(request, message)
        return redirect("feed_productions")

    return render(request, "feed/stage1.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def process_stage2_view(request, pk):
    farm = get_current_farm(request)
    production = production_or_404(farm, pk)

    if production.status == ProductionModel.Statuses.COMPLETED:
        messages.info(request, "To śrutowanie jest już zakończone.")
        return redirect("feed_productions")
    if production.status == ProductionModel.Statuses.QUEUED:
        messages.warning(request, "Najpierw zakończ Etap 1 śrutowania.")
        return redirect("process_stage1", pk=pk)

    context = production_details_for_stages(farm, pk)
    if request.method == "POST":
        if not _checklist_is_complete(request, context["stage2_items"]):
            messages.error(request, "Potwierdź dodanie wszystkich składników ręcznych.")
            return render(request, "feed/stage2.html", context, status=400)
        success, message = complete_production(
            farm,
            pk,
            user=request.user,
        )
        if success:
            production.refresh_from_db()
            log_action(
                farm=farm,
                user=request.user,
                action="PRODUCTION_COMPLETED",
                obj=production,
            )
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect("feed_productions")

    return render(request, "feed/stage2.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def reverse_production_settlement_view(request, pk):
    farm = get_current_farm(request)
    production = production_or_404(farm, pk)
    if production.status != ProductionModel.Statuses.COMPLETED:
        messages.info(request, "Cofnąć można wyłącznie zakończone śrutowanie.")
        return redirect("feed_productions")

    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        try:
            ProductionSettlementReversalWorkflow(
                farm=farm,
                user=request.user,
            ).reverse(production.pk, reason=reason)
        except ValidationError as error:
            messages.error(request, error.messages[0])
        else:
            messages.success(
                request,
                "Rozliczenie zostało cofnięte. Śrutowanie wróciło do etapu składników ręcznych.",
            )
            return redirect("feed_productions")

    return render(request, "feed/production_reversal.html", {"production": production})


@login_required
def production_detail_view(request, pk):
    farm = get_current_farm(request)
    return render(
        request,
        "feed/production_detail.html",
        production_details_for_stages(farm, pk),
    )


@login_required
@require_POST
def bulk_complete_productions_view(request):
    farm = get_current_farm(request)
    production_ids = request.POST.getlist("production_ids")
    completion_mode = request.POST.get("completion_mode", "skip")
    if completion_mode == "ready":
        production_ids = list(
            ProductionModel.objects.filter(
                pk__in=production_ids,
                recipe__farm=farm,
                status=ProductionModel.Statuses.STAGE_1_DONE,
            ).values_list("pk", flat=True)
        )
    result = bulk_complete_productions(
        farm,
        production_ids,
        user=request.user,
    )

    completed = list(
        ProductionModel.objects.filter(
            pk__in=result["completed_ids"],
            recipe__farm=farm,
        ).select_related("recipe")
    )
    for production in completed:
        log_action(
            farm=farm,
            user=request.user,
            action="PRODUCTION_COMPLETED",
            obj=production,
            metadata={"bulk": True},
        )

    completed_count = len(result["completed_ids"])
    already_count = len(result["already_completed"])
    failed_count = len(result["failed"])

    if completed_count:
        messages.success(request, f"Zakończono {completed_count} śrutowań.")
    if already_count:
        messages.info(request, f"Pominięto {already_count} już zakończonych śrutowań.")
    if result["unavailable_count"]:
        messages.warning(
            request,
            f"Pominięto {result['unavailable_count']} nieprawidłowych lub niedostępnych pozycji.",
        )
    if failed_count:
        failure_details = " | ".join(
            f"{item['label']}: {item['message']}" for item in result["failed"]
        )
        messages.error(
            request,
            f"Nie udało się zakończyć {failed_count} śrutowań. {failure_details}",
        )
    if not completed_count and not already_count and not failed_count and not result["unavailable_count"]:
        messages.warning(request, "Nie zaznaczono żadnego śrutowania do zakończenia.")

    return redirect("feed_productions")
