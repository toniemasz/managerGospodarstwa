from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from farms.forms import FarmSettingsForm
from farms.services.current_farm import get_current_farm
from farms.services.settings_service import get_farm_settings


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
