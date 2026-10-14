from django.shortcuts import get_object_or_404

from sales.models import PigSaleModel


def sales_for_farm(farm, *, date_from=None, date_to=None):
    """Zwraca sprzedaże gospodarstwa opcjonalnie ograniczone zakresem dat."""

    queryset = PigSaleModel.objects.filter(farm=farm)
    if date_from is not None:
        queryset = queryset.filter(sale_date__gte=date_from)
    if date_to is not None:
        queryset = queryset.filter(sale_date__lte=date_to)
    return queryset


def sale_for_farm(farm, sale_id: int, *, with_rows: bool = False) -> PigSaleModel:
    """Pobiera sprzedaż wyłącznie z bieżącego gospodarstwa."""

    queryset = PigSaleModel.objects.filter(farm=farm)
    if with_rows:
        queryset = queryset.prefetch_related("rows")
    return get_object_or_404(queryset, pk=sale_id)
