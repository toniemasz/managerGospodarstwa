from django.core.management.base import BaseCommand, CommandError

from farms.models import FarmModel
from feed.services.integrity import FeedIntegrityService


class Command(BaseCommand):
    help = "Audytuje spójność FIFO, kosztów i gotowej paszy. Domyślnie niczego nie zapisuje."

    def add_arguments(self, parser):
        parser.add_argument("--farm-id", type=int)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        farms = FarmModel.objects.order_by("id")
        if options["farm_id"]:
            farms = farms.filter(pk=options["farm_id"])
            if not farms.exists():
                raise CommandError("Nie znaleziono gospodarstwa o podanym ID.")
        total_issues = 0
        total_repaired = 0
        for farm in farms:
            result = FeedIntegrityService(farm).audit(apply=options["apply"])
            self.stdout.write(f"Gospodarstwo {farm.pk} ({farm.name}): {result.issue_count} problemów")
            for issue in result.issues:
                marker = "naprawialny" if issue.repairable else "wymaga decyzji"
                self.stdout.write(
                    f"- [{issue.code}] {issue.object_label}#{issue.object_id or '-'}: {issue.message} ({marker})"
                )
            total_issues += result.issue_count
            total_repaired += result.repaired
        mode = "ZAPIS" if options["apply"] else "TYLKO ODCZYT"
        self.stdout.write(self.style.SUCCESS(
            f"Tryb: {mode}. Problemy: {total_issues}. Naprawiono: {total_repaired}."
        ))
