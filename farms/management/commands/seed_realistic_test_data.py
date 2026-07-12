from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from costs.models import CostCategoryModel, CostModel
from farms.models import AuditLogModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from feed.actions.inventory import InventoryActions
from feed.actions.recipe_versions import RecipeVersionActions
from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    InventoryMovementModel,
    ProductionIngredientUsageModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
    RecipeVersionItemModel,
    RecipeVersionModel,
)
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import MortalityReportModel, SowEventModel, SowModel, VaccinationPlanModel


START_DATE = date(2025, 1, 1)
USERNAME = "testtest"
PASSWORD = "testtest"

INGREDIENTS = [
    {"name": "Pszenica", "bin": True, "threshold": "3500.00", "quantity": "52000.00", "price": "0.82000"},
    {"name": "Jęczmień", "bin": True, "threshold": "3000.00", "quantity": "46000.00", "price": "0.76000"},
    {"name": "Kukurydza", "bin": True, "threshold": "2800.00", "quantity": "43000.00", "price": "0.88000"},
    {"name": "Śruta sojowa", "bin": False, "threshold": "900.00", "quantity": "15000.00", "price": "2.15000"},
    {"name": "Śruta rzepakowa", "bin": False, "threshold": "800.00", "quantity": "13000.00", "price": "1.42000"},
    {"name": "Otręby pszenne", "bin": False, "threshold": "700.00", "quantity": "12000.00", "price": "0.69000"},
    {"name": "Premiks lochy", "bin": False, "threshold": "180.00", "quantity": "3400.00", "price": "4.85000"},
    {"name": "Premiks tuczniki", "bin": False, "threshold": "220.00", "quantity": "4200.00", "price": "4.30000"},
    {"name": "Kreda pastewna", "bin": False, "threshold": "200.00", "quantity": "5000.00", "price": "0.52000"},
    {"name": "Sól paszowa", "bin": False, "threshold": "120.00", "quantity": "2600.00", "price": "0.48000"},
    {"name": "Olej rzepakowy", "bin": False, "threshold": "150.00", "quantity": "3200.00", "price": "4.10000"},
]

RECIPES = {
    "Lochy prośne": [
        ("Pszenica", "35.00"),
        ("Jęczmień", "30.00"),
        ("Otręby pszenne", "17.00"),
        ("Śruta rzepakowa", "12.00"),
        ("Premiks lochy", "4.00"),
        ("Kreda pastewna", "1.40"),
        ("Sól paszowa", "0.60"),
    ],
    "Lochy karmiące": [
        ("Pszenica", "28.00"),
        ("Kukurydza", "24.00"),
        ("Śruta sojowa", "23.00"),
        ("Jęczmień", "15.00"),
        ("Premiks lochy", "5.00"),
        ("Olej rzepakowy", "3.00"),
        ("Kreda pastewna", "1.30"),
        ("Sól paszowa", "0.70"),
    ],
    "Warchlaki": [
        ("Pszenica", "29.00"),
        ("Kukurydza", "25.00"),
        ("Jęczmień", "16.00"),
        ("Śruta sojowa", "20.00"),
        ("Premiks tuczniki", "6.00"),
        ("Olej rzepakowy", "2.00"),
        ("Kreda pastewna", "1.30"),
        ("Sól paszowa", "0.70"),
    ],
    "Tuczniki finisher": [
        ("Pszenica", "38.00"),
        ("Jęczmień", "28.00"),
        ("Kukurydza", "16.00"),
        ("Śruta rzepakowa", "12.00"),
        ("Premiks tuczniki", "4.00"),
        ("Kreda pastewna", "1.40"),
        ("Sól paszowa", "0.60"),
    ],
}

COST_CATEGORIES = [
    "Weterynarz",
    "Leki i szczepionki",
    "Energia",
    "Paliwo",
    "Słoma",
    "Transport",
    "Serwis i remonty",
    "Usługi zootechniczne",
    "Ubezpieczenie",
    "Pozostałe",
]


class Command(BaseCommand):
    help = "Czyści i tworzy realistyczny lokalny zestaw testowy dla użytkownika testtest."

    def add_arguments(self, parser):
        parser.add_argument("--username", default=USERNAME)
        parser.add_argument("--password", default=PASSWORD)
        parser.add_argument("--end-date", default=None, help="Data końcowa symulacji, np. 2026-07-08.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Ta komenda działa wyłącznie lokalnie przy DEBUG=True.")

        end_date = self._parse_end_date(options["end_date"])
        if end_date < START_DATE:
            raise CommandError("Data końcowa nie może być wcześniejsza niż 2025-01-01.")

        with transaction.atomic():
            user = self._user(options["username"], options["password"])
            farm = get_or_create_user_farm(user)
            self._clear_farm_data(farm)
            self._configure_farm(farm)
            context = self._seed(user=user, farm=farm, end_date=end_date)
            counts = self._validate_dataset(farm=farm, end_date=end_date, context=context)

        self.stdout.write(self.style.SUCCESS(
            "Realistyczne dane testowe gotowe: "
            + ", ".join(f"{key}={value}" for key, value in counts.items())
        ))

    @staticmethod
    def _parse_end_date(value: str | None) -> date:
        if not value:
            return timezone.localdate()
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise CommandError("Nieprawidłowa data --end-date. Użyj formatu RRRR-MM-DD.") from error

    @staticmethod
    def _user(username: str, password: str):
        User = get_user_model()
        user, _ = User.objects.get_or_create(username=username)
        user.set_password(password)
        user.is_active = True
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["password", "is_active", "is_staff", "is_superuser"])
        return user

    def _clear_farm_data(self, farm):
        CostModel.objects.filter(farm=farm).delete()
        CostCategoryModel.objects.filter(farm=farm).delete()
        SaleClassRowModel.objects.filter(sale__farm=farm).delete()
        PigSaleModel.objects.filter(farm=farm).delete()
        MortalityReportModel.objects.filter(farm=farm).delete()
        SowEventModel.objects.filter(sow__farm=farm).delete()
        SowModel.objects.filter(farm=farm).delete()
        VaccinationPlanModel.objects.filter(farm=farm).delete()
        ProductionIngredientUsageModel.objects.filter(farm=farm).delete()
        InventoryMovementModel.objects.filter(farm=farm).delete()
        ProductionModel.objects.filter(recipe__farm=farm).delete()
        RecipeVersionItemModel.objects.filter(recipe_version__recipe__farm=farm).delete()
        RecipeVersionModel.objects.filter(recipe__farm=farm).delete()
        RecipeItemModel.objects.filter(recipe__farm=farm).delete()
        RecipeModel.objects.filter(farm=farm).delete()
        DeliveryModel.objects.filter(ingredient__farm=farm).delete()
        IngredientPriceConfigModel.objects.filter(ingredient__farm=farm).delete()
        IngredientModel.objects.filter(farm=farm).delete()
        AuditLogModel.objects.filter(farm=farm).delete()

    @staticmethod
    def _configure_farm(farm):
        farm.name = "Gospodarstwo trzody 2401"
        farm.save(update_fields=["name"])
        settings_obj = get_farm_settings(farm)
        settings_obj.pregnancy_check_after_days = 30
        settings_obj.gestation_days = 114
        settings_obj.farrowing_alert_days_ahead = 10
        settings_obj.vaccination_alert_days_ahead = 14
        settings_obj.interface_scale = "comfortable"
        settings_obj.theme = "light"
        settings_obj.font_scale = 100
        settings_obj.visible_modules = [
            "tasks", "statistics", "sows", "feed", "inventory", "deliveries",
            "recipes", "production", "sales", "costs", "settings",
        ]
        settings_obj.nav_modules = ["tasks", "sows", "feed", "sales", "costs"]
        settings_obj.save()

    def _seed(self, *, user, farm, end_date: date) -> dict:
        vaccination_plans = self._vaccination_plans(farm)
        sows = self._sows(farm=farm, end_date=end_date, vaccination_plans=vaccination_plans)
        ingredients = self._ingredients(farm=farm, user=user, end_date=end_date)
        recipes = self._recipes(farm=farm, user=user, ingredients=ingredients)
        productions = self._productions(farm=farm, recipes=recipes, end_date=end_date)
        rebuild_result = InventoryActions(farm).rebuild(prefer_existing_movements=False)
        sales = self._sales(farm=farm, end_date=end_date)
        categories = self._cost_categories(farm)
        costs = self._costs(farm=farm, user=user, categories=categories, end_date=end_date)
        mortality_reports = self._mortality_reports(farm=farm, user=user, end_date=end_date)
        return {
            "sows": sows,
            "ingredients": ingredients,
            "recipes": recipes,
            "productions": productions,
            "sales": sales,
            "categories": categories,
            "costs": costs,
            "mortality_reports": mortality_reports,
            "rebuild_result": rebuild_result,
        }

    @staticmethod
    def _vaccination_plans(farm) -> dict[str, VaccinationPlanModel]:
        plan_payloads = [
            {"name": "Parwowiroza przed oproszeniem", "days_before_farrowing": 21, "reminder_days_ahead": 14},
            {"name": "Kolibakterioza przed oproszeniem", "days_before_farrowing": 14, "reminder_days_ahead": 14},
            {"name": "Różyca po inseminacji", "days_after_event": 28, "event_source": "INSEMINATION", "reminder_days_ahead": 10},
            {
                "name": "Różyca cykliczna",
                "interval_months": 6,
                "interval_value": 6,
                "interval_unit": "MONTHS",
                "schedule_mode": "FROM_LAST_COMPLETED",
                "first_due_date": date(2025, 1, 1),
                "reminder_days_ahead": 14,
            },
        ]
        plans = {}
        for payload in plan_payloads:
            plan = VaccinationPlanModel.objects.create(farm=farm, **payload)
            plans[plan.name] = plan
        return plans

    def _sows(self, *, farm, end_date: date, vaccination_plans: dict[str, VaccinationPlanModel]) -> list[SowModel]:
        sows = [
            SowModel.objects.create(farm=farm, ear_tag=str(2401 + index), entry_date=date(2024, 8, 15) + timedelta(days=index * 9))
            for index in range(10)
        ]
        cycles = {
            0: [(date(2025, 1, 6), "TAK", 13, 1, 12), (date(2025, 7, 7), "TAK", 12, 0, 11), (date(2025, 12, 10), "TAK", 14, 1, 13), (date(2026, 6, 8), None, None, None, None)],
            1: [(date(2025, 1, 20), "TAK", 12, 1, 11), (date(2025, 8, 5), "TAK", 13, 0, 12), (date(2026, 5, 1), "TAK", None, None, None)],
            2: [(date(2025, 2, 3), "TAK", 14, 0, 13), (date(2025, 9, 1), "TAK", 12, 1, 11), (date(2026, 3, 3), "TAK", 13, 0, None)],
            3: [(date(2025, 2, 17), "NIE", None, None, None), (date(2025, 4, 1), "TAK", 11, 1, 10), (date(2025, 10, 15), "TAK", 12, 0, 11), (date(2026, 4, 15), "TAK", 13, 1, 12)],
            4: [(date(2025, 3, 1), "TAK", None, None, None), (date(2025, 6, 20), "TAK", 13, 0, 12), (date(2026, 1, 3), "TAK", 12, 0, 11), (date(2026, 5, 20), "TAK", None, None, None)],
            5: [(date(2025, 3, 12), "?", None, None, None), (date(2025, 5, 2), "TAK", 12, 1, 11), (date(2025, 11, 12), "TAK", 13, 0, 12), (date(2026, 6, 1), "?", None, None, None)],
            6: [(date(2025, 4, 3), "TAK", 11, 0, 10), (date(2025, 10, 28), "TAK", 14, 1, 13), (date(2026, 6, 1), None, None, None, None)],
            7: [(date(2025, 4, 20), "TAK", 13, 1, 12), (date(2025, 11, 20), "TAK", 12, 0, 11), (date(2026, 3, 23), "TAK", None, None, None)],
            8: [(date(2025, 5, 8), "NIE", None, None, None), (date(2025, 7, 1), "TAK", 12, 2, 10), (date(2026, 1, 18), "TAK", 13, 1, 12), (date(2026, 6, 15), None, None, None, None)],
            9: [(date(2025, 5, 20), "TAK", 13, 0, 12), (date(2025, 12, 12), "TAK", None, None, None), (date(2026, 4, 5), "TAK", 12, 1, 11)],
        }
        for index, sow in enumerate(sows):
            for cycle_index, (insemination_date, result, born_alive, born_dead, weaned) in enumerate(cycles[index]):
                self._cycle(
                    sow=sow,
                    insemination_date=insemination_date,
                    result=result,
                    born_alive=born_alive,
                    born_dead=born_dead,
                    weaned=weaned,
                    cycle_index=cycle_index,
                    end_date=end_date,
                )
            self._vaccinations(sow=sow, plans=vaccination_plans, end_date=end_date)
        self._event(
            sows[4],
            "MISCARRIAGE",
            date(2025, 6, 8),
            {"note": "Poronienie po potwierdzonej ciąży, kontrola weterynaryjna wykonana."},
            end_date=end_date,
        )
        return sows

    def _cycle(
        self,
        *,
        sow: SowModel,
        insemination_date: date,
        result: str | None,
        born_alive: int | None,
        born_dead: int | None,
        weaned: int | None,
        cycle_index: int,
        end_date: date,
    ):
        self._event(
            sow,
            "INSEMINATION",
            insemination_date,
            {"technician": "Marek" if cycle_index % 2 == 0 else "Piotr"},
            end_date=end_date,
        )
        if result:
            self._event(
                sow,
                "PREGNANCY_CHECK",
                insemination_date + timedelta(days=31),
                {"result": result},
                end_date=end_date,
            )
        if result == "TAK" and born_alive is not None:
            farrowing_date = insemination_date + timedelta(days=114)
            self._event(
                sow,
                "FARROWING",
                farrowing_date,
                {"born_alive": born_alive, "born_dead": born_dead or 0},
                end_date=end_date,
            )
            if weaned is not None:
                self._event(
                    sow,
                    "WEANING",
                    farrowing_date + timedelta(days=28),
                    {"count": weaned},
                    end_date=end_date,
                )

    def _vaccinations(self, *, sow: SowModel, plans: dict[str, VaccinationPlanModel], end_date: date):
        dates = [
            (date(2025, 1, 15), "Różyca cykliczna"),
            (date(2025, 7, 16), "Różyca cykliczna"),
            (date(2026, 1, 14), "Różyca cykliczna"),
            (date(2026, 6, 24), "Różyca po inseminacji"),
        ]
        for vaccination_date, vaccine_name in dates:
            plan = plans[vaccine_name]
            self._event(
                sow,
                "VACCINATION",
                vaccination_date,
                {
                    "vaccine_name": vaccine_name,
                    "cycle_id": f"{sow.ear_tag}-{plan.pk}-{vaccination_date:%Y%m%d}",
                    "note": "Zapis szczepienia zgodny z planem stada.",
                },
                end_date=end_date,
            )

    @staticmethod
    def _event(sow: SowModel, event_type: str, event_date: date, details: dict, *, end_date: date):
        if START_DATE <= event_date <= end_date:
            SowEventModel.objects.create(
                sow=sow,
                event_type=event_type,
                event_date=event_date,
                details=details,
            )

    def _ingredients(self, *, farm, user, end_date: date) -> dict[str, IngredientModel]:
        ingredients = {}
        for payload in INGREDIENTS:
            ingredient = IngredientModel.objects.create(
                farm=farm,
                name=payload["name"],
                low_stock_threshold_kg=Decimal(payload["threshold"]),
                is_in_bin=payload["bin"],
            )
            IngredientPriceConfigModel.objects.create(
                ingredient=ingredient,
                price_per_kg=Decimal(payload["price"]),
            )
            ingredients[payload["name"]] = ingredient
            delivery_date = START_DATE
            delivery_number = 1
            while delivery_date <= end_date:
                DeliveryModel.objects.create(
                    ingredient=ingredient,
                    date=delivery_date,
                    quantity_kg=Decimal(payload["quantity"]),
                    price_per_kg=Decimal(payload["price"]) + Decimal(delivery_number - 1) * Decimal("0.01500"),
                )
                delivery_date += timedelta(days=45)
                delivery_number += 1
        InventoryActions(farm).rebuild(prefer_existing_movements=False)
        return ingredients

    def _recipes(self, *, farm, user, ingredients: dict[str, IngredientModel]) -> dict[str, RecipeModel]:
        recipes = {}
        version_actions = RecipeVersionActions(farm=farm, user=user)
        for recipe_name, item_payloads in RECIPES.items():
            recipe = RecipeModel.objects.create(farm=farm, name=recipe_name)
            for ingredient_name, percentage in item_payloads:
                RecipeItemModel.objects.create(
                    recipe=recipe,
                    ingredient=ingredients[ingredient_name],
                    percentage=Decimal(percentage),
                )
            version_actions.ensure_current_version(recipe, change_note="Pierwsza obowiązująca receptura")
            recipes[recipe_name] = recipe
        return recipes

    @staticmethod
    def _productions(*, farm, recipes: dict[str, RecipeModel], end_date: date) -> list[ProductionModel]:
        recipe_names = list(recipes)
        productions = []
        production_date = date(2025, 1, 10)
        index = 0
        while production_date <= min(end_date, date(2026, 6, 10)):
            recipe = recipes[recipe_names[index % len(recipe_names)]]
            status = ProductionModel.Statuses.COMPLETED
            production = ProductionModel(
                recipe=recipe,
                recipe_version=recipe.versions.get(is_current=True),
                date=production_date,
                time=time(7 + index % 6, 30),
                quantity_kg=Decimal("1350.00") + Decimal(index % 4) * Decimal("150.00"),
                status=status,
                completed_at=timezone.make_aware(datetime.combine(production_date, time(15, 0))),
            )
            production._skip_inventory_sync = True
            production.save()
            productions.append(production)
            production_date += timedelta(days=21)
            index += 1

        for planned_date, status, recipe_name in [
            (date(2026, 6, 25), ProductionModel.Statuses.STAGE_1_DONE, "Tuczniki finisher"),
            (end_date, ProductionModel.Statuses.QUEUED, "Lochy karmiące"),
        ]:
            if START_DATE <= planned_date <= end_date:
                production = ProductionModel(
                    recipe=recipes[recipe_name],
                    recipe_version=recipes[recipe_name].versions.get(is_current=True),
                    date=planned_date,
                    time=time(8, 0),
                    quantity_kg=Decimal("1500.00"),
                    status=status,
                )
                production._skip_inventory_sync = True
                production.save()
                productions.append(production)
        return productions

    def _sales(self, *, farm, end_date: date) -> list[PigSaleModel]:
        sales = []
        sale_dates = [
            date(2025, 3, 12), date(2025, 5, 28), date(2025, 8, 14), date(2025, 10, 30),
            date(2026, 1, 22), date(2026, 3, 18), date(2026, 5, 20), date(2026, 6, 30),
        ]
        for index, sale_date in enumerate(date_value for date_value in sale_dates if date_value <= end_date):
            sale = PigSaleModel.objects.create(
                farm=farm,
                sale_date=sale_date,
                document_number=f"FV/{sale_date.year}/{index + 1:03d}",
                tattoo="PL142536",
                meat_class="E",
                avg_meatiness_seurop=Decimal("58.40") + Decimal(index) * Decimal("0.12"),
                live_weight=Decimal("0.00"),
                dressing_percentage=Decimal("78.10"),
            )
            self._sale_rows(sale=sale, index=index)
            sale.recalculate_from_rows()
            sale.live_weight = (sale.total_weight / Decimal("0.7810")).quantize(Decimal("0.01"))
            sale.save(update_fields=[
                "quantity", "total_weight", "price_per_kg", "live_weight",
                "net_value", "vat_value", "gross_value", "avg_meatiness_seurop",
                "dressing_percentage",
            ])
            sales.append(sale)
        return sales

    @staticmethod
    def _sale_rows(*, sale: PigSaleModel, index: int):
        base_quantity = 44 + index * 2
        rows = [
            ("S", int(base_quantity * Decimal("0.18")), Decimal("98.30"), Decimal("8.15")),
            ("E", int(base_quantity * Decimal("0.54")), Decimal("96.80"), Decimal("7.85")),
            ("U", base_quantity - int(base_quantity * Decimal("0.18")) - int(base_quantity * Decimal("0.54")), Decimal("94.20"), Decimal("7.35")),
        ]
        for line_no, (meat_class, quantity, avg_weight, price) in enumerate(rows, start=1):
            weight = (Decimal(quantity) * avg_weight).quantize(Decimal("0.01"))
            net = (weight * price).quantize(Decimal("0.01"))
            vat = (net * Decimal("0.08")).quantize(Decimal("0.01"))
            SaleClassRowModel.objects.create(
                sale=sale,
                line_no=line_no,
                meat_class=meat_class,
                quantity=quantity,
                weight=weight,
                avg_weight=avg_weight,
                avg_meatiness=Decimal("59.30") - Decimal(line_no) * Decimal("0.80"),
                price_per_kg=price,
                net_value=net,
                vat_value=vat,
                gross_value=net + vat,
            )

    @staticmethod
    def _cost_categories(farm) -> dict[str, CostCategoryModel]:
        return {
            name: CostCategoryModel.objects.create(
                farm=farm,
                name=name,
                description=f"Koszty operacyjne: {name.lower()}",
                is_active=True,
            )
            for name in COST_CATEGORIES
        }

    @staticmethod
    def _costs(*, farm, user, categories: dict[str, CostCategoryModel], end_date: date) -> list[CostModel]:
        costs = []
        suppliers = [
            "AgroWet Sp. z o.o.",
            "Energia dla Rolnictwa",
            "Rol-Trans",
            "Słoma Kujawy",
            "Serwis Paszowy",
            "Przychodnia Weterynaryjna Pod Lasem",
        ]
        category_names = list(categories)
        month_cursor = START_DATE
        index = 0
        while month_cursor <= end_date:
            for offset in range(2):
                cost_date = min(month_cursor + timedelta(days=5 + offset * 11), end_date)
                category = categories[category_names[(index + offset) % len(category_names)]]
                costs.append(CostModel.objects.create(
                    farm=farm,
                    category=category,
                    date=cost_date,
                    amount=Decimal("420.00") + Decimal(index * 63 + offset * 145),
                    description=f"{category.name} - rozliczenie {cost_date:%m.%Y}",
                    document_number=f"K/{cost_date.year}/{index + 1:03d}-{offset + 1}",
                    supplier=suppliers[(index + offset) % len(suppliers)],
                    is_paid=cost_date < end_date - timedelta(days=21),
                    created_by=user,
                ))
            month_cursor = self_next_month(month_cursor)
            index += 1
        return costs

    @staticmethod
    def _mortality_reports(*, farm, user, end_date: date) -> list[MortalityReportModel]:
        reports = []
        for index, report_date in enumerate([
            date(2025, 2, 18), date(2025, 6, 9), date(2025, 9, 27),
            date(2026, 2, 11), date(2026, 5, 16),
        ]):
            if report_date <= end_date:
                reports.append(MortalityReportModel.objects.create(
                    farm=farm,
                    mortality_type=MortalityReportModel.TYPE_POST_WEANING,
                    mortality_date=report_date,
                    quantity=1 + index % 3,
                    reason="Straty po odsadzeniu",
                    note="Zapis kontroli stanu po odsadzeniu.",
                    created_by=user,
                ))
        return reports

    def _validate_dataset(self, *, farm, end_date: date, context: dict) -> dict[str, int]:
        self._require(SowModel.objects.filter(farm=farm).count() == 10, "Oczekiwano dokładnie 10 macior.")
        self._require(not SowModel.objects.filter(farm=farm, ear_tag__icontains="demo").exists(), "Numer maciory zawiera tekst demo.")
        self._require("demo" not in farm.name.lower(), "Nazwa gospodarstwa zawiera tekst demo.")
        for event_type, _label in SowEventModel.EVENT_TYPES:
            self._require(
                SowEventModel.objects.filter(sow__farm=farm, event_type=event_type).exists(),
                f"Brakuje zdarzenia typu {event_type}.",
            )
        self._require(
            not SowEventModel.objects.filter(sow__farm=farm, event_date__gt=end_date).exists(),
            "Istnieją zdarzenia po dacie końcowej.",
        )
        self._require(
            SowModel.objects.filter(farm=farm, events__isnull=True).count() == 0,
            "Każda maciora powinna mieć historię zdarzeń.",
        )
        completed = ProductionModel.objects.filter(recipe__farm=farm, status=ProductionModel.Statuses.COMPLETED)
        self._require(completed.exists(), "Brakuje zakończonych śrutowań.")
        self._require(not completed.filter(feed_cost_is_partial=True).exists(), "Zakończone śrutowania mają częściowy koszt FIFO.")
        self._require(
            not completed.filter(ingredient_usages__isnull=True).exists(),
            "Zakończone śrutowanie nie ma rozliczeń FIFO.",
        )
        balances = InventoryActions(farm).balances()
        self._require(all(value >= 0 for value in balances.values()), "Magazyn ma ujemny stan składnika.")
        self._require(
            not DeliveryModel.objects.filter(ingredient__farm=farm, remaining_quantity_kg__lt=0).exists(),
            "Dostawa ma ujemny stan FIFO.",
        )
        sales = PigSaleModel.objects.filter(farm=farm)
        self._require(sales.exists(), "Brakuje sprzedaży.")
        self._require(not sales.filter(rows__isnull=True).exists(), "Każda sprzedaż powinna mieć wiersze rozliczenia.")
        self._require(not sales.filter(no_settlement=True).exists(), "Sprzedaże testowe mają być kompletne, bez flagi braku rozliczenia.")
        self._require(not CostModel.objects.filter(farm=farm, category__isnull=True).exists(), "Każdy koszt musi mieć kategorię.")
        self._require(not CostModel.objects.filter(farm=farm, document_number="").exists(), "Każdy koszt musi mieć numer dokumentu.")
        self._require(
            not PigSaleModel.objects.filter(farm=farm, document_number__icontains="demo").exists(),
            "Numer dokumentu sprzedaży zawiera tekst demo.",
        )
        self._require(
            not CostModel.objects.filter(farm=farm, description__icontains="demo").exists(),
            "Opis kosztu zawiera tekst demo.",
        )
        years = set(SowEventModel.objects.filter(sow__farm=farm).dates("event_date", "year").values_list("event_date__year", flat=True))
        self._require({2025, 2026}.issubset(years), "Historia zdarzeń powinna obejmować lata 2025 i 2026.")
        return {
            "maciory": SowModel.objects.filter(farm=farm).count(),
            "zdarzenia": SowEventModel.objects.filter(sow__farm=farm).count(),
            "szczepienia": VaccinationPlanModel.objects.filter(farm=farm).count(),
            "składniki": IngredientModel.objects.filter(farm=farm).count(),
            "dostawy": DeliveryModel.objects.filter(ingredient__farm=farm).count(),
            "receptury": RecipeModel.objects.filter(farm=farm).count(),
            "śrutowania": ProductionModel.objects.filter(recipe__farm=farm).count(),
            "ruchy_magazynowe": InventoryMovementModel.objects.filter(farm=farm).count(),
            "sprzedaże": sales.count(),
            "koszty": CostModel.objects.filter(farm=farm).count(),
            "upadki": MortalityReportModel.objects.filter(farm=farm).count(),
            "fifo_użycia": context["rebuild_result"]["production_movements"],
        }

    @staticmethod
    def _require(condition: bool, message: str):
        if not condition:
            raise CommandError(message)


def self_next_month(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    return date(year, month, 1)
