from django.core.paginator import Paginator

from sows.models import PigletTransferModel


def piglet_transfer_list(*, farm, params):
    transfers = PigletTransferModel.objects.filter(farm=farm).select_related(
        "source_farrowing__sow",
        "target_farrowing__sow",
        "created_by",
        "canceled_by",
    )
    source = (params.get("source") or "").strip()
    target = (params.get("target") or "").strip()
    if source:
        transfers = transfers.filter(source_farrowing__sow__ear_tag__icontains=source)
    if target:
        transfers = transfers.filter(target_farrowing__sow__ear_tag__icontains=target)
    if params.get("status") == "active":
        transfers = transfers.filter(canceled_at__isnull=True)
    elif params.get("status") == "canceled":
        transfers = transfers.filter(canceled_at__isnull=False)
    return Paginator(transfers, 25).get_page(params.get("page"))
