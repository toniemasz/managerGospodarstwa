import logging
import traceback
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .application.services import SaleDashboardService
from .forms import PigSaleForm

logger = logging.getLogger(__name__)


@login_required
def sales_list_view(request):
    try:
        service = SaleDashboardService()
        context = service.get_dashboard_summary()
        return render(request, 'sales/sales_list.html', context)
    except Exception as e:
        logger.error(f"Error in sales dashboard: {e}")
        return HttpResponse(f"Błąd systemu: {str(e)}<br><pre>{traceback.format_exc()}</pre>", status=500)


@login_required
def add_sale_view(request):
    if request.method == 'POST':
        form = PigSaleForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('sales_list')
    else:
        form = PigSaleForm()

    return render(request, 'sales/add_sale.html', {'form': form})