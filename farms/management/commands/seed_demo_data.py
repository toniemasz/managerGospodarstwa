from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError, call_command
from django.db import transaction

from costs.models import CostCategoryModel, CostModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from feed.models import DeliveryModel, IngredientModel, ProductionModel, RecipeItemModel, RecipeModel
from feed.actions.inventory import InventoryActions
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


INGREDIENTS = [
    ("Pszenica", True), ("Jęczmień", True), ("Kukurydza", True), ("Pszenżyto", True),
    ("Śruta sojowa", False), ("Śruta rzepakowa", False), ("Otręby pszenne", False),
    ("Premiks lochy", False), ("Premiks tuczniki", False), ("Kreda pastewna", False),
    ("Fosforan", False), ("Sól", False), ("Olej rzepakowy", False),
    ("Zakwaszacz", False), ("Lizyna", False),
]

RECIPES = {
    "Lochy prośne": [(0, 35), (1, 30), (6, 15), (5, 15), (7, 5)],
    "Lochy karmiące": [(0, 30), (2, 25), (4, 25), (6, 15), (7, 5)],
    "Prosięta starter": [(0, 20), (2, 30), (4, 30), (8, 10), (12, 5), (14, 5)],
    "Warchlaki": [(0, 30), (1, 25), (2, 15), (4, 20), (8, 10)],
    "Tuczniki grower": [(0, 35), (1, 30), (2, 15), (5, 15), (8, 5)],
    "Tuczniki finisher": [(0, 40), (1, 35), (3, 10), (5, 10), (8, 5)],
}

COST_CATEGORIES = [
    "Weterynarz",
    "Energia",
    "Paliwo",
    "Słoma",
    "Remonty",
    "Usługi",
    "Leki",
    "Transport",
    "Inne",
]


class Command(BaseCommand):
    help = "Tworzy realistyczne, idempotentne dane demonstracyjne."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Czyści lokalną bazę przed seedowaniem.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo_data działa wyłącznie lokalnie przy DEBUG=True.")
        if options["reset"]:
            call_command("flush", interactive=False, verbosity=0)
        with transaction.atomic():
            counts = self._seed()
        self.stdout.write(self.style.SUCCESS(
            "Dane demo gotowe: " + ", ".join(f"{key}={value}" for key, value in counts.items())
        ))

    def _seed(self):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username="testtest")
        user.set_password("testtest")
        user.is_active = True
        user.save(update_fields=["password", "is_active"])
        farm = get_or_create_user_farm(user)
        farm.name = "Gospodarstwo demonstracyjne"
        farm.save(update_fields=["name"])
        get_farm_settings(farm)

        today = date.today()
        plans = [
            {"name": "Parwowiroza przed oproszeniem", "days_before_farrowing": 21},
            {"name": "E. coli po oproszeniu", "days_after_event": 7, "event_source": "FARROWING"},
            {"name": "Parwowiroza po inseminacji", "days_after_event": 14, "event_source": "INSEMINATION"},
            {
                "name": "Różyca cykliczna",
                "interval_months": 4,
                "interval_value": 4,
                "interval_unit": "MONTHS",
                "schedule_mode": "FROM_LAST_COMPLETED",
                "first_due_date": today,
            },
        ]
        for data in plans:
            VaccinationPlanModel.objects.update_or_create(farm=farm, name=data["name"], defaults=data)

        sows = []
        for index in range(40):
            sow, _ = SowModel.objects.update_or_create(
                farm=farm,
                ear_tag=f"DEMO-{index + 1:03d}",
                defaults={
                    "entry_date": today - timedelta(days=500 - index * 5),
                    "is_archived": index >= 35,
                },
            )
            sows.append(sow)
            if 6 <= index < 12:
                self._event(sow, "INSEMINATION", today - timedelta(days=10 + index), {"technician": "Jan"})
            elif 12 <= index < 18:
                self._event(sow, "INSEMINATION", today - timedelta(days=35 + index), {"technician": "Anna"})
            elif 18 <= index < 24:
                insemination = today - timedelta(days=90 + index)
                self._event(sow, "INSEMINATION", insemination, {"technician": "Jan"})
                self._event(sow, "PREGNANCY_CHECK", insemination + timedelta(days=30), {"result": "TAK"})
            elif 24 <= index < 29:
                insemination = today - timedelta(days=45 + index)
                self._event(sow, "INSEMINATION", insemination, {"technician": "Anna"})
                self._event(sow, "PREGNANCY_CHECK", insemination + timedelta(days=30), {"result": "?"})
            elif 29 <= index < 35:
                farrowing = today - timedelta(days=7 + index)
                self._event(sow, "INSEMINATION", farrowing - timedelta(days=114), {"technician": "Jan"})
                self._event(sow, "PREGNANCY_CHECK", farrowing - timedelta(days=80), {"result": "TAK"})
                self._event(sow, "FARROWING", farrowing, {"born_alive": 11 + index % 4, "born_dead": index % 2})
            else:
                if index < 6:
                    old_farrowing = today - timedelta(days=220 + index)
                    self._event(sow, "FARROWING", old_farrowing, {"born_alive": 12, "born_dead": 1})
                    self._event(sow, "WEANING", old_farrowing + timedelta(days=28), {"count": 11})
                negative_date = today - timedelta(days=60 + index)
                self._event(sow, "INSEMINATION", negative_date - timedelta(days=30), {"technician": "Jan"})
                self._event(sow, "PREGNANCY_CHECK", negative_date, {"result": "NIE"})
            if index % 4 == 0:
                self._event(sow, "VACCINATION", today - timedelta(days=120 + index), {"vaccine_name": "Różyca cykliczna", "cycle_id": f"demo-{index}"})

        ingredients = []
        for index, (name, in_bin) in enumerate(INGREDIENTS):
            ingredient, _ = IngredientModel.objects.update_or_create(
                farm=farm,
                name=name,
                defaults={"is_in_bin": in_bin, "low_stock_threshold_kg": Decimal("600") if in_bin else Decimal("150")},
            )
            ingredients.append(ingredient)
            for delivery_index in range(4):
                DeliveryModel.objects.update_or_create(
                    ingredient=ingredient,
                    date=today - timedelta(days=delivery_index * 75 + index),
                    defaults={
                        "quantity_kg": Decimal("12000") if in_bin else Decimal("5000"),
                        "price_per_kg": Decimal("0.85") + Decimal(index) / Decimal("20") + Decimal(delivery_index) / Decimal("10"),
                    },
                )

        recipes = []
        for name, composition in RECIPES.items():
            recipe, _ = RecipeModel.objects.get_or_create(farm=farm, name=name)
            recipes.append(recipe)
            for ingredient_index, percentage in composition:
                RecipeItemModel.objects.update_or_create(
                    recipe=recipe,
                    ingredient=ingredients[ingredient_index],
                    defaults={"percentage": Decimal(percentage)},
                )

        statuses = [ProductionModel.Statuses.QUEUED] * 5 + [ProductionModel.Statuses.STAGE_1_DONE] * 5 + [ProductionModel.Statuses.COMPLETED] * 10
        for index, status in enumerate(statuses):
            production, _ = ProductionModel.objects.update_or_create(
                recipe=recipes[index % len(recipes)],
                date=today - timedelta(days=index * 9),
                time=time(7 + index % 10, 0),
                defaults={"quantity_kg": Decimal("2000") + Decimal(index % 3) * Decimal("500"), "status": status},
            )
            if status == ProductionModel.Statuses.COMPLETED and not production.completed_at:
                from django.utils import timezone
                production.completed_at = timezone.now() - timedelta(days=index * 9)
                production.save(update_fields=["completed_at"])

        for index in range(12):
            sale, _ = PigSaleModel.objects.update_or_create(
                farm=farm,
                document_number=f"DEMO/{index + 1:03d}",
                defaults={
                    "sale_date": today - timedelta(days=index * 24),
                    "tattoo": "PL-DEMO",
                    "no_settlement": index % 3 == 0,
                    "quantity": 0 if index % 3 == 0 else 80 + index,
                    "total_weight": Decimal("0") if index % 3 == 0 else Decimal(80 + index) * Decimal("95.5"),
                    "price_per_kg": Decimal("7.20") + Decimal(index) / Decimal("20"),
                    "avg_meatiness_seurop": None if index % 3 == 0 else Decimal("58.20") + Decimal(index) / Decimal("10"),
                    "live_weight": Decimal("0") if index % 3 == 0 else Decimal(80 + index) * Decimal("122.5"),
                    "dressing_percentage": None if index % 3 == 0 else Decimal("77.96"),
                    "net_value": Decimal("0") if index % 3 == 0 else Decimal("52000") + Decimal(index) * Decimal("1250"),
                    "vat_value": Decimal("0") if index % 3 == 0 else Decimal("4160") + Decimal(index) * Decimal("100"),
                    "gross_value": Decimal("0") if index % 3 == 0 else Decimal("56160") + Decimal(index) * Decimal("1350"),
                },
            )
            if not sale.no_settlement:
                SaleClassRowModel.objects.update_or_create(
                    sale=sale, line_no=1,
                    defaults={"meat_class": "E", "quantity": sale.quantity, "weight": sale.total_weight, "price_per_kg": sale.price_per_kg, "net_value": sale.net_value, "vat_value": sale.vat_value, "gross_value": sale.gross_value},
                )

        categories = []
        for name in COST_CATEGORIES:
            category, _ = CostCategoryModel.objects.update_or_create(
                farm=farm,
                name=name,
                defaults={"description": f"Koszty: {name.lower()}", "is_active": True},
            )
            categories.append(category)
        for index in range(18):
            month = (index % 12) + 1
            cost_date = date(today.year, month, min(5 + index, 25))
            category = categories[index % len(categories)]
            CostModel.objects.update_or_create(
                farm=farm,
                category=category,
                date=cost_date,
                description=f"Wydatek demonstracyjny {index + 1:02d}",
                defaults={
                    "amount": Decimal("450.00") + Decimal(index) * Decimal("137.50"),
                    "document_number": f"KOSZT/{today.year}/{index + 1:03d}",
                    "supplier": f"Dostawca {index % 6 + 1}",
                    "is_paid": index % 4 != 0,
                    "created_by": user,
                },
            )
        InventoryActions(farm).rebuild()
        return {
            "maciory": len(sows),
            "składniki": len(ingredients),
            "receptury": len(recipes),
            "produkcje": len(statuses),
            "sprzedaże": 12,
            "kategorie kosztów": CostCategoryModel.objects.filter(farm=farm).count(),
            "koszty": CostModel.objects.filter(farm=farm).count(),
        }

    @staticmethod
    def _event(sow, event_type, event_date, details):
        SowEventModel.objects.update_or_create(
            sow=sow,
            event_type=event_type,
            event_date=event_date,
            defaults={"details": details},
        )
