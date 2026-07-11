from django.db.models import Q

from feed.models import IngredientModel, ProductionModel, RecipeModel


class FeedSearchProvider:
    def __init__(self, farm):
        self.farm = farm

    def ingredients(self, query, *, limit):
        return IngredientModel.objects.filter(
            Q(farm=self.farm), Q(name__icontains=query) | Q(description__icontains=query),
        ).order_by("name")[:limit]

    def recipes(self, query, *, limit):
        return RecipeModel.objects.filter(
            farm=self.farm, name__icontains=query,
        ).order_by("name")[:limit]

    def productions(self, query, *, limit):
        return ProductionModel.objects.filter(
            Q(recipe__farm=self.farm),
            Q(recipe__name__icontains=query) | Q(status__icontains=query),
        ).select_related("recipe").order_by("-date", "-id")[:limit]
