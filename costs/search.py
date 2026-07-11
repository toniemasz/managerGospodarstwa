from django.db.models import Q

from costs.models import CostCategoryModel, CostModel


def search_costs(farm, query, *, limit):
    return CostModel.objects.filter(
        Q(farm=farm),
        Q(description__icontains=query) | Q(document_number__icontains=query)
        | Q(supplier__icontains=query) | Q(category__name__icontains=query),
    ).select_related("category").order_by("-date", "-id")[:limit]


def search_cost_categories(farm, query, *, limit):
    return CostCategoryModel.objects.filter(
        Q(farm=farm), Q(name__icontains=query) | Q(description__icontains=query),
    ).order_by("name")[:limit]
