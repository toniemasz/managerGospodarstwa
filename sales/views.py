import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import PigSaleForm, SaleClassRowFormSet
from .models import PigSaleModel
from .services.sale_dashboard_service import SaleDashboardService
from .services.sale_form_service import SaleFormService
from farms.services.current_farm import get_current_farm
from farms.services.date_range import PERIOD_OPTIONS, parse_date_range
from farms.services.audit_log_service import log_action

logger = logging.getLogger(__name__)


@login_required
def sales_list_view(request):
    try:
        date_range = parse_date_range(request.GET, default_period='6m')
        service = SaleDashboardService(farm=get_current_farm(request))
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
    farm = get_current_farm(request)
    sale = PigSaleModel(farm=farm)
    return _sale_form_view(request, sale=sale, template_context={'is_edit': False})


@login_required
def edit_sale_view(request, pk):
    farm = get_current_farm(request)
    sale = get_object_or_404(PigSaleModel.objects.prefetch_related('rows'), pk=pk, farm=farm)
    return _sale_form_view(request, sale=sale, template_context={'is_edit': True})


@login_required
def delete_sale_view(request, pk):
    farm = get_current_farm(request)
    sale = get_object_or_404(PigSaleModel, pk=pk, farm=farm)
    if request.method == 'POST':
        representation = str(sale)
        object_id = sale.pk
        sale.delete()
        log_action(farm=farm, user=request.user, action="DELETE", model_label="sales.PigSaleModel", object_id=object_id, object_repr=representation)
        messages.success(request, "Sprzedaż została usunięta.")
    return redirect('sales_list')


def _sale_form_view(request, sale: PigSaleModel, template_context: dict):
    service = SaleFormService(farm=sale.farm)
    if request.method == 'POST' and 'import_pdf' in request.POST:
        return _handle_pdf_import(request, sale, template_context, service)

    if request.method == 'POST':
        form = PigSaleForm(request.POST, request.FILES, instance=sale)
        row_formset = service.row_formset_from_post(request.POST)
        if form.is_valid() and row_formset.is_valid():
            saved_sale = service.save_sale(form, row_formset, sale)
            log_action(
                farm=saved_sale.farm,
                user=request.user,
                action="UPDATE" if template_context.get('is_edit') else "CREATE",
                obj=saved_sale,
            )
            messages.success(request, "Sprzedaż została zapisana.")
            return redirect('sales_list')
    else:
        form = PigSaleForm(instance=sale)
        row_formset = SaleClassRowFormSet(prefix='rows', initial=service.initial_rows_for_sale(sale))

    context = {
        'form': form,
        'row_formset': row_formset,
        'sale': sale,
        **template_context,
    }
    return render(request, 'sales/add_sale.html', context)


def _handle_pdf_import(request, sale: PigSaleModel, template_context: dict, service: SaleFormService):
    uploaded_pdf = request.FILES.get('settlement_pdf')
    if not uploaded_pdf:
        messages.error(request, "Wybierz plik PDF do importu.")
        form = PigSaleForm(request.POST, request.FILES, instance=sale)
        row_formset = service.row_formset_from_post(request.POST)
    else:
        try:
            PigSaleForm.validate_settlement_pdf(uploaded_pdf)
            parsed = service.parse_pdf_import(uploaded_pdf, request.POST)
        except ValidationError as error:
            messages.error(request, error.messages[0])
            form = PigSaleForm(request.POST, request.FILES, instance=sale)
            row_formset = service.row_formset_from_post(request.POST)
            context = {'form': form, 'row_formset': row_formset, 'sale': sale, **template_context}
            return render(request, 'sales/add_sale.html', context)
        except Exception:
            logger.exception("Nie udało się odczytać rozliczenia PDF")
            messages.error(request, "Nie udało się odczytać PDF. Sprawdź, czy plik ma obsługiwany format.")
            form = PigSaleForm(request.POST, request.FILES, instance=sale)
            row_formset = service.row_formset_from_post(request.POST)
            context = {'form': form, 'row_formset': row_formset, 'sale': sale, **template_context}
            return render(request, 'sales/add_sale.html', context)
        form = PigSaleForm(instance=sale, initial=parsed.form_initial)
        row_formset = SaleClassRowFormSet(prefix='rows', initial=parsed.row_initial)

        if parsed.has_rows:
            messages.success(request, "Zaimportowano rozliczenie z PDF. Sprawdź tabelę przed zapisem.")
        for warning in parsed.warnings:
            messages.warning(request, warning)
        log_action(
            farm=sale.farm,
            user=request.user,
            action="PDF_IMPORT_PREVIEW",
            model_label="sales.PigSaleModel",
            object_id=sale.pk,
            object_repr=str(sale),
            metadata={"filename": uploaded_pdf.name, "warnings": parsed.warnings},
        )

    context = {
        'form': form,
        'row_formset': row_formset,
        'sale': sale,
        **template_context,
    }
    return render(request, 'sales/add_sale.html', context)
