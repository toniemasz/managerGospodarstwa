from sows.models import SowModel, VaccinationPlanModel


def search_sows(farm, query, *, limit):
    return SowModel.objects.filter(
        farm=farm, ear_tag__icontains=query,
    ).order_by("is_archived", "ear_tag")[:limit]


def search_vaccination_plans(farm, query, *, limit):
    return VaccinationPlanModel.objects.filter(
        farm=farm, name__icontains=query,
    ).order_by("name")[:limit]
