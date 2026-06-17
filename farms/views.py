import json
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from farms.forms import FarmSettingsForm
from farms.models import FarmModel, FarmSettingsModel
from farms.services.current_farm import get_current_farm
from farms.services.settings_service import get_farm_settings
from feed.models import DeliveryModel, IngredientModel, IngredientPriceConfigModel, ProductionModel, RecipeItemModel, RecipeModel
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


@login_required
def farm_settings_view(request):
    farm = get_current_farm(request)
    settings = get_farm_settings(farm)

    if request.method == 'POST':
        form = FarmSettingsForm(request.POST, instance=settings, farm=farm)
        if form.is_valid():
            form.save()
            messages.success(request, "Ustawienia gospodarstwa zostały zapisane.")
            return redirect('farm_settings')
    else:
        form = FarmSettingsForm(instance=settings, farm=farm)

    return render(request, 'farms/settings.html', {'form': form})


@login_required
def export_user_data_view(request):
    farm = get_current_farm(request)
    timestamp = timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
    json_filename = f'eksport_danych_{request.user.username}_{timestamp}.json'
    zip_filename = f'eksport_danych_{request.user.username}_{timestamp}.zip'

    export_data = {
        'generated_at': timezone.now().isoformat(),
        'user': {
            'username': request.user.get_username(),
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        },
        'farm': {
            'id': farm.id if farm else None,
            'name': farm.name if farm else None,
        },
        'data': _build_user_export_payload(farm),
    }

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as export_zip:
        export_zip.writestr(json_filename, json.dumps(export_data, ensure_ascii=False, indent=2))

    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'
    return response


def _build_user_export_payload(farm):
    querysets = {
        'farms.FarmModel': FarmModel.objects.filter(id=farm.id),
        'farms.FarmSettingsModel': FarmSettingsModel.objects.filter(farm=farm),
        'sows.VaccinationPlanModel': VaccinationPlanModel.objects.filter(farm=farm).order_by('id'),
        'sows.SowModel': SowModel.objects.filter(farm=farm).order_by('id'),
        'sows.SowEventModel': SowEventModel.objects.filter(sow__farm=farm).order_by('id'),
        'feed.IngredientModel': IngredientModel.objects.filter(farm=farm).order_by('id'),
        'feed.DeliveryModel': DeliveryModel.objects.filter(ingredient__farm=farm).order_by('id'),
        'feed.IngredientPriceConfigModel': IngredientPriceConfigModel.objects.filter(ingredient__farm=farm).order_by('id'),
        'feed.RecipeModel': RecipeModel.objects.filter(farm=farm).order_by('id'),
        'feed.RecipeItemModel': RecipeItemModel.objects.filter(recipe__farm=farm).order_by('id'),
        'feed.ProductionModel': ProductionModel.objects.filter(recipe__farm=farm).order_by('id'),
        'sales.PigSaleModel': PigSaleModel.objects.filter(farm=farm).order_by('id'),
        'sales.SaleClassRowModel': SaleClassRowModel.objects.filter(sale__farm=farm).order_by('id'),
    }
    return {label: _serialize_queryset(queryset) for label, queryset in querysets.items()}


def _serialize_queryset(queryset):
    serialized = serializers.serialize(
        'json',
        queryset,
        use_natural_foreign_keys=True,
        use_natural_primary_keys=True,
    )
    return json.loads(serialized)
