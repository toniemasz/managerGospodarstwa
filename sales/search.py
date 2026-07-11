from django.db.models import Q

from sales.models import PigSaleModel


def search_sales(farm, query, *, limit):
    return PigSaleModel.objects.filter(
        Q(farm=farm),
        Q(document_number__icontains=query) | Q(tattoo__icontains=query),
    ).order_by("-sale_date", "-id")[:limit]
