from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from farms.services.audit_log_service import log_action
from farms.services.current_farm import get_current_farm
from feed.actions.finished_feed import create_feed_serving, delete_feed_serving, purchase_ready_feed
from feed.forms import FeedServingForm, ReadyFeedPurchaseForm
from feed.models import FeedServingModel
from feed.selectors.finished_feed import feed_servings_context, finished_feed_inventory_context
from common.units import format_mass


@login_required
def finished_feed_inventory_view(request):
    return render(request, "feed/finished_feed_inventory.html", finished_feed_inventory_context(get_current_farm(request)))


@login_required
@require_http_methods(["GET", "POST"])
def purchase_ready_feed_view(request):
    farm = get_current_farm(request)
    form = ReadyFeedPurchaseForm(request.POST or None, farm=farm, initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        delivery = purchase_ready_feed(farm=farm, user=request.user, **form.cleaned_data)
        log_action(farm=farm, user=request.user, action="READY_FEED_PURCHASE", obj=delivery)
        messages.success(request, f"Przyjęto {format_mass(delivery.quantity_kg)} gotowej paszy „{delivery.product.name}”.")
        return redirect("finished_feed_inventory")
    return render(request, "feed/ready_feed_purchase_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def create_feed_serving_view(request):
    farm = get_current_farm(request)
    form = FeedServingForm(request.POST or None, farm=farm, initial={"date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            serving = create_feed_serving(farm=farm, user=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error.messages[0])
        else:
            log_action(farm=farm, user=request.user, action="FEED_SERVING_CREATE", obj=serving)
            messages.success(request, f"Zarejestrowano podanie {format_mass(serving.quantity_kg)} paszy „{serving.product.name}”.")
            return redirect("feed_servings")
    return render(request, "feed/feed_serving_form.html", {"form": form})


@login_required
def feed_servings_view(request):
    return render(request, "feed/feed_servings.html", feed_servings_context(get_current_farm(request)))


@login_required
@require_POST
def delete_feed_serving_view(request, pk):
    farm = get_current_farm(request)
    serving = get_object_or_404(FeedServingModel, pk=pk, farm=farm)
    representation = str(serving)
    delete_feed_serving(farm=farm, serving=serving)
    log_action(farm=farm, user=request.user, action="FEED_SERVING_DELETE", model_label="feed.FeedServingModel", object_id=pk, object_repr=representation)
    messages.success(request, "Usunięto podanie i przywrócono ilości do pierwotnych partii.")
    return redirect("feed_servings")
