from django.core.management import BaseCommand

from farms.models import FarmModel
from feed.services.inventory_service import InventoryMovementService


class Command(BaseCommand):
    help = "Odbudowuje ruchy magazynowe oraz rozliczenia FIFO z dostaw i zakończonych produkcji."

    def add_arguments(self, parser):
        parser.add_argument("--farm-id", type=int)

    def handle(self, *args, **options):
        farms = FarmModel.objects.all()
        if options["farm_id"]:
            farms = farms.filter(pk=options["farm_id"])
        for farm in farms:
            counts = InventoryMovementService(farm).rebuild()
            self.stdout.write(f"{farm}: {counts}")
