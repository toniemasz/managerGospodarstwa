from farms.models import FarmSettingsModel


def get_farm_settings(farm) -> FarmSettingsModel | None:
    if farm is None:
        return None
    settings, _ = FarmSettingsModel.objects.get_or_create(farm=farm)
    return settings
