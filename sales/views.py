import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PigSaleForm, SaleClassRowFormSet, empty_sale_row_initials
from .models import PigSaleModel, SaleClassRowModel
from .services.pdf_import_service import SaleSettlementPdfParser
from .services.sale_dashboard_service import SaleDashboardService
from farms.services.farm_service import get_or_create_user_farm
from farms.services.date_range import PERIOD_OPTIONS, parse_date_range

logger = logging.getLogger(__name__)


def _current_farm(request):
    farm = getattr(request, 'farm', None)
    if farm is None and request.user.is_authenticated:
        farm = get_or_create_user_farm(request.user)
        request.farm = farm
    return farm


@login_required
def sales_list_view(request):
    try:
        date_range = parse_date_range(request.GET, default_period='6m')
        service = SaleDashboardService(farm=_current_farm(request))
        context = service.get_dashboard_summary(
            date_from=date_range.date_from,
            date_to=date_range.date_to,
        )
        context['date_filter'] = date_range
        context['period_options'] = PERIOD_OPTIONS
        return render(request, 'sales/sales_list.html', context)
    except Exception:
        logger.exception("Error in sales dashboard")
        return HttpResponse("Błąd systemu. Szczegóły zapisano w logach aplikacji.", status=500)


@login_required
def add_sale_view(request):
    farm = _current_farm(request)
    sale = PigSaleModel(farm=farm)
    return _sale_form_view(request, sale=sale, template_context={'is_edit': False})


@login_required
def edit_sale_view(request, pk):
    farm = _current_farm(request)
    sale = get_object_or_404(PigSaleModel.objects.prefetch_related('rows'), pk=pk, farm=farm)
    return _sale_form_view(request, sale=sale, template_context={'is_edit': True})


@login_required
def delete_sale_view(request, pk):
    farm = _current_farm(request)
    sale = get_object_or_404(PigSaleModel, pk=pk, farm=farm)
    if request.method == 'POST':
        sale.delete()
        messages.success(request, "Sprzedaż została usunięta.")
    return redirect('sales_list')


def _sale_form_view(request, sale: PigSaleModel, template_context: dict):
    if request.method == 'POST' and 'import_pdf' in request.POST:
        return _handle_pdf_import(request, sale, template_context)

    if request.method == 'POST':
        form = PigSaleForm(request.POST, request.FILES, instance=sale)
        row_formset = _row_formset_from_post(request.POST)
        if form.is_valid() and row_formset.is_valid():
            saved_sale = form.save(commit=False)
            saved_sale.farm = sale.farm
            saved_sale.save()
            _replace_sale_rows(saved_sale, row_formset)
            messages.success(request, "Sprzedaż została zapisana.")
            return redirect('sales_list')
    else:
        form = PigSaleForm(instance=sale)
        row_formset = SaleClassRowFormSet(prefix='rows', initial=_initial_rows_for_sale(sale))

    context = {
        'form': form,
        'row_formset': row_formset,
        'sale': sale,
        **template_context,
    }
    return render(request, 'sales/add_sale.html', context)


def _handle_pdf_import(request, sale: PigSaleModel, template_context: dict):
    uploaded_pdf = request.FILES.get('settlement_pdf')
    if not uploaded_pdf:
        messages.error(request, "Wybierz plik PDF do importu.")
        form = PigSaleForm(request.POST, request.FILES, instance=sale)
        row_formset = _row_formset_from_post(request.POST)
    else:
        parsed = SaleSettlementPdfParser().parse(uploaded_pdf)
        initial = _form_initial_from_post(request.POST)
        initial.update(_without_empty_values(parsed.sale_fields))
        initial['no_settlement'] = False

        form = PigSaleForm(instance=sale, initial=initial)
        row_initial = parsed.rows or empty_sale_row_initials()
        row_formset = SaleClassRowFormSet(prefix='rows', initial=row_initial)

        if parsed.rows:
            messages.success(request, "Zaimportowano rozliczenie z PDF. Sprawdź tabelę przed zapisem.")
        for warning in parsed.warnings:
            messages.warning(request, warning)

    context = {
        'form': form,
        'row_formset': row_formset,
        'sale': sale,
        **template_context,
    }
    return render(request, 'sales/add_sale.html', context)


def _replace_sale_rows(sale: PigSaleModel, row_formset) -> None:
    sale.rows.all().delete()

    rows = []
    for index, form in enumerate(row_formset.forms, start=1):
        if form.cleaned_data.get('DELETE') or not form.has_row_data():
            continue
        rows.append(SaleClassRowModel(
            sale=sale,
            line_no=form.cleaned_data.get('line_no') or len(rows) + 1 or index,
            meat_class=form.cleaned_data.get('meat_class') or '',
            quantity=form.cleaned_data.get('quantity'),
            weight=form.cleaned_data.get('weight'),
            avg_weight=form.cleaned_data.get('avg_weight'),
            avg_meatiness=form.cleaned_data.get('avg_meatiness'),
            price_per_kg=form.cleaned_data.get('price_per_kg'),
            net_value=form.cleaned_data.get('net_value'),
            vat_value=form.cleaned_data.get('vat_value'),
            gross_value=form.cleaned_data.get('gross_value'),
        ))

    if rows:
        SaleClassRowModel.objects.bulk_create(rows)
        sale.recalculate_from_rows()
        sale.meat_class = rows[0].meat_class or sale.meat_class
        sale.save(update_fields=[
            'quantity',
            'total_weight',
            'meat_class',
            'price_per_kg',
            'net_value',
            'vat_value',
            'gross_value',
        ])


def _initial_rows_for_sale(sale: PigSaleModel) -> list[dict]:
    if sale.pk and sale.rows.exists():
        return [
            {
                'line_no': row.line_no,
                'meat_class': row.meat_class,
                'quantity': row.quantity,
                'weight': row.weight,
                'avg_weight': row.avg_weight,
                'avg_meatiness': row.avg_meatiness,
                'price_per_kg': row.price_per_kg,
                'net_value': row.net_value,
                'vat_value': row.vat_value,
                'gross_value': row.gross_value,
            }
            for row in sale.rows.all()
        ]

    if sale.pk and sale.quantity:
        return [{
            'line_no': 1,
            'meat_class': sale.meat_class,
            'quantity': sale.quantity,
            'weight': sale.total_weight,
            'price_per_kg': sale.price_per_kg,
            'gross_value': sale.total_price,
        }]

    return empty_sale_row_initials()


def _form_initial_from_post(post_data) -> dict:
    fields = [
        'sale_date',
        'document_number',
        'tattoo',
        'avg_meatiness_seurop',
        'live_weight',
        'dressing_percentage',
    ]
    initial = {field: post_data.get(field) for field in fields if post_data.get(field)}
    initial['no_settlement'] = post_data.get('no_settlement') == 'on'
    return initial


def _without_empty_values(values: dict) -> dict:
    return {key: value for key, value in values.items() if value not in (None, '')}


def _row_formset_from_post(post_data):
    if 'rows-TOTAL_FORMS' in post_data:
        return SaleClassRowFormSet(post_data, prefix='rows')

    data = post_data.copy()
    data['rows-TOTAL_FORMS'] = '1'
    data['rows-INITIAL_FORMS'] = '0'
    data['rows-MIN_NUM_FORMS'] = '0'
    data['rows-MAX_NUM_FORMS'] = '1000'
    data['rows-0-line_no'] = '1'
    data['rows-0-meat_class'] = post_data.get('meat_class', '')
    data['rows-0-quantity'] = post_data.get('quantity', '')
    data['rows-0-weight'] = post_data.get('total_weight', '')
    data['rows-0-price_per_kg'] = post_data.get('price_per_kg', '')
    return SaleClassRowFormSet(data, prefix='rows')
