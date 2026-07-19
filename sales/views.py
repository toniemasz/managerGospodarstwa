import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from sales.actions import delete_sale
from .forms import PigSaleForm, SaleClassRowFormSet
from .models import PigSaleModel
from .services.sale_dashboard_service import SaleDashboardService
from .services.sale_form_service import SaleFormService
from common.filter_ui import filter_ui_state, parse_filter_date
from farms.services.current_farm import get_current_farm
from farms.services.accounting_year import get_available_years, parse_accounting_year
from farms.services.audit_log_service import log_action

logger = logging.getLogger(__name__)


@login_required
def sales_list_view(request):
    try:
        farm = get_current_farm(request)
        accounting_year, date_from, date_to = _sales_date_range_from_request(request)
        service = SaleDashboardService(farm=farm)
        context = service.get_dashboard_summary(
            date_from=date_from,
            date_to=date_to,
        )
        context.update({
            'selected_year': accounting_year.year,
            'available_years': get_available_years(farm),
            'date_from': date_from,
            'date_to': date_to,
        })
        context.update(filter_ui_state(request.GET, {
            'year': 'Rok', 'date_from': 'Od', 'date_to': 'Do',
        }))
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
    if request.method == 'POST':
        deleted_sale = delete_sale(farm, pk)
        log_action(
            farm=farm,
            user=request.user,
            action="DELETE",
            model_label=deleted_sale.model_label,
            object_id=deleted_sale.object_id,
            object_repr=deleted_sale.object_repr,
        )
        messages.success(request, "Sprzedaż została usunięta.")
    return redirect('sales_list')


def _sales_date_range_from_request(request):
    accounting_year = parse_accounting_year(request.GET)
    date_from = parse_filter_date(request.GET.get('date_from')) or accounting_year.date_from
    date_to = parse_filter_date(request.GET.get('date_to')) or accounting_year.date_to
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    return accounting_year, date_from, date_to


def _sale_form_view(request, sale: PigSaleModel, template_context: dict):
    service = SaleFormService(farm=sale.farm)
    if request.method == 'POST' and 'import_pdf' in request.POST:
        return _handle_pdf_import(request, sale, template_context, service)

    if request.method == 'POST':
        form, row_formset = _sale_forms_from_post(request, sale, service)
        if form.is_valid() and row_formset.is_valid():
            try:
                saved_sale = service.save_sale(form, row_formset, sale)
            except ValidationError as error:
                if hasattr(error, 'message_dict'):
                    for field_name, field_errors in error.message_dict.items():
                        for field_error in field_errors:
                            form.add_error(field_name if field_name in form.fields else None, field_error)
                else:
                    form.add_error(None, error.messages[0])
            else:
                log_action(
                    farm=saved_sale.farm,
                    user=request.user,
                    action="UPDATE" if template_context.get('is_edit') else "CREATE",
                    obj=saved_sale,
                )
                messages.success(request, "Sprzedaż została zapisana.")
                return redirect('sales_list')
    else:
        form, row_formset = _sale_forms_from_instance(sale, service)

    return _render_sale_form(request, form, row_formset, sale, template_context)


def _handle_pdf_import(request, sale: PigSaleModel, template_context: dict, service: SaleFormService):
    uploaded_pdf = request.FILES.get('settlement_pdf')

    if not uploaded_pdf:
        messages.error(request, "Wybierz plik PDF do importu.")
        return _render_posted_sale_form(request, sale, template_context, service)

    try:
        PigSaleForm.validate_settlement_pdf(uploaded_pdf)
        parsed = service.parse_pdf_import(uploaded_pdf, request.POST)
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return _render_posted_sale_form(request, sale, template_context, service)
    except Exception:
        logger.exception("Nie udało się odczytać rozliczenia PDF")
        messages.error(request, "Nie udało się odczytać PDF. Sprawdź, czy plik ma obsługiwany format.")
        return _render_posted_sale_form(request, sale, template_context, service)

    form = PigSaleForm(instance=sale, initial=parsed.form_initial, farm=sale.farm)
    row_formset = SaleClassRowFormSet(prefix='rows', initial=parsed.row_initial)
    log_action(
        farm=sale.farm,
        user=request.user,
        action="PDF_IMPORT_PREVIEW",
        model_label="sales.PigSaleModel",
        object_id=sale.pk,
        object_repr=str(sale),
        metadata={"filename": uploaded_pdf.name, "warnings": parsed.warnings},
    )
    return _render_sale_form(
        request,
        form,
        row_formset,
        sale,
        template_context,
        pdf_import_feedback=parsed.as_feedback(),
        pdf_import_problem_line_numbers=parsed.problem_line_numbers,
    )


def _sale_forms_from_post(request, sale: PigSaleModel, service: SaleFormService):
    return (
        PigSaleForm(request.POST, request.FILES, instance=sale, farm=sale.farm),
        service.row_formset_from_post(request.POST),
    )


def _sale_forms_from_instance(sale: PigSaleModel, service: SaleFormService):
    return (
        PigSaleForm(instance=sale, farm=sale.farm),
        SaleClassRowFormSet(prefix='rows', initial=service.initial_rows_for_sale(sale)),
    )


def _render_posted_sale_form(request, sale: PigSaleModel, template_context: dict, service: SaleFormService):
    form, row_formset = _sale_forms_from_post(request, sale, service)
    return _render_sale_form(request, form, row_formset, sale, template_context)


def _render_sale_form(
    request,
    form,
    row_formset,
    sale: PigSaleModel,
    template_context: dict,
    *,
    pdf_import_feedback=None,
    pdf_import_problem_line_numbers=None,
):
    context = {
        'form': form,
        'row_formset': row_formset,
        'sale': sale,
        'pdf_import_feedback': pdf_import_feedback,
        'pdf_import_problem_line_numbers': pdf_import_problem_line_numbers or [],
        **template_context,
    }
    return render(request, 'sales/add_sale.html', context)
