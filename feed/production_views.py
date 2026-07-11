from django.contrib import messages
from django.contrib.auth.decorators import login_required
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

    if request.method == "POST":
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

    return render(request, "feed/stage1.html", production_details_for_stages(farm, pk))


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

    if request.method == "POST":
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

    context = production_details_for_stages(farm, pk)
    return render(request, "feed/stage2.html", context)


@login_required
@require_POST
def bulk_complete_productions_view(request):
    farm = get_current_farm(request)
    result = bulk_complete_productions(
        farm,
        request.POST.getlist("production_ids"),
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
