from django.core.management.base import BaseCommand

from feed.models import FinishedFeedBatchModel, ProductionModel
from feed.selectors.recipe_requirements import recipe_item_dicts_for_production


class Command(BaseCommand):
    help = "Raportuje klasyfikację historycznych produkcji, partie, podania i kompletność kosztów."

    def add_arguments(self, parser):
        parser.add_argument("--farm-id", type=int)
        parser.add_argument("--dry-run", action="store_true", help="Opcja zgodności; raport nigdy nie zapisuje danych.")

    def handle(self, *args, **options):
        productions = ProductionModel.objects.filter(status=ProductionModel.Statuses.COMPLETED).select_related("recipe", "recipe__farm")
        if options.get("farm_id"):
            productions = productions.filter(recipe__farm_id=options["farm_id"])
        rows = list(productions.prefetch_related("recipe__items", "recipe_version__items"))
        single = [row for row in rows if len(recipe_item_dicts_for_production(row)) == 1]
        mixed = [row for row in rows if len(recipe_item_dicts_for_production(row)) > 1]
        empty = [row for row in rows if not recipe_item_dicts_for_production(row)]
        missing_cost = [row for row in rows if row.feed_cost_total == 0]
        partial_cost = [row for row in rows if row.feed_cost_is_partial or "brak" in row.feed_cost_note.casefold()]
        self.stdout.write(f"Zakończone produkcje: {len(rows)}")
        self.stdout.write(f"Jednoskładnikowe -> gotowa pasza i pełne historyczne podanie: {len(single)}")
        self.stdout.write(f"Wieloskładnikowe -> normalna produkcja i partia magazynowa: {len(mixed)}")
        self.stdout.write(f"Bez zapisanego składu -> partia z kosztem częściowym do kontroli: {len(empty)}")
        self.stdout.write(f"Produkcje z utworzoną partią: {FinishedFeedBatchModel.objects.filter(production_id__in=[row.pk for row in rows]).count()}")
        self.stdout.write(f"Koszt 0 zł wymagający kontroli: {len(missing_cost)}")
        self.stdout.write(f"Koszt częściowy wymagający kontroli: {len(partial_cost)}")
        self.stdout.write("Raport nie zmienia danych. Konwersję wykonuje migracja feed.0008.")
