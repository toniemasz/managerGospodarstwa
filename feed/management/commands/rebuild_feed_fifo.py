from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from farms.models import FarmModel
from feed.models import ProductionModel
from feed.services.inventory_service import InventoryMovementService, InventoryRebuildError


class Command(BaseCommand):
    help = "Przebudowuje rozliczenia FIFO dostaw, produkcji paszy i kosztów składników."

    def add_arguments(self, parser):
        parser.add_argument(
            "--farm-id",
            type=int,
            action="append",
            dest="farm_ids",
            help="ID gospodarstwa do przebudowy. Można podać kilka razy.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Zapisuje zmiany. Bez tej flagi komenda wykonuje tylko podgląd i wycofuje transakcję.",
        )

    def handle(self, *args, **options):
        farm_ids = options.get("farm_ids")
        apply_changes = options["apply"]
        farms = FarmModel.objects.all().order_by("id")
        if farm_ids:
            farms = farms.filter(id__in=farm_ids)
            missing_ids = set(farm_ids) - set(farms.values_list("id", flat=True))
            if missing_ids:
                raise CommandError(f"Nie znaleziono gospodarstw: {', '.join(map(str, sorted(missing_ids)))}")

        if not farms.exists():
            self.stdout.write(self.style.WARNING("Brak gospodarstw do przebudowy."))
            return

        if not apply_changes:
            self.stdout.write(self.style.WARNING("Tryb podglądu: zmiany zostaną wycofane. Dodaj --apply, aby je zapisać."))

        for farm in farms:
            try:
                with transaction.atomic():
                    result = InventoryMovementService(farm).rebuild()
                    partial_count = ProductionModel.objects.filter(
                        recipe__farm=farm,
                        status=ProductionModel.Statuses.COMPLETED,
                        feed_cost_is_partial=True,
                    ).count()
                    if not apply_changes:
                        transaction.set_rollback(True)
            except InventoryRebuildError as error:
                cause = f": {error.__cause__}" if error.__cause__ else ""
                raise CommandError(f"Nie udało się przebudować FIFO: {error}{cause}") from error
            except Exception as error:
                raise CommandError(
                    f"Nie udało się przebudować FIFO "
                    f"(farm.id={farm.id}, farm.name={farm.name}): {error}"
                ) from error

            label = "zapisano" if apply_changes else "podgląd"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{farm.id} {farm.name}: {label}; dostawy={result['deliveries']}, "
                    f"rozliczenia={result['production_movements']}, częściowe koszty={partial_count}"
                )
            )
