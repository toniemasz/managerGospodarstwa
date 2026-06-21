from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


def assign_missing_farms(apps, schema_editor):
    Farm = apps.get_model("farms", "FarmModel")
    Ingredient = apps.get_model("feed", "IngredientModel")
    Recipe = apps.get_model("feed", "RecipeModel")
    if not Ingredient.objects.filter(farm__isnull=True).exists() and not Recipe.objects.filter(farm__isnull=True).exists():
        return
    farm = Farm.objects.order_by("owner_id", "id").first()
    if farm is None:
        app_label, model_name = settings.AUTH_USER_MODEL.split(".")
        User = apps.get_model(app_label, model_name)
        user = User.objects.order_by("id").first()
        if user is None:
            user = User.objects.create(username="gospodarstwo", password="!")
        farm = Farm.objects.create(owner_id=user.pk, name="Gospodarstwo")
    for model, max_length in ((Ingredient, 100), (Recipe, 150)):
        for obj in model.objects.filter(farm__isnull=True).order_by("id"):
            if model.objects.filter(farm=farm, name=obj.name).exists():
                suffix = f" (legacy {obj.pk})"
                obj.name = f"{obj.name[:max_length - len(suffix)]}{suffix}"
            obj.farm = farm
            obj.save(update_fields=["farm", "name"])


def build_initial_movements(apps, schema_editor):
    Delivery = apps.get_model("feed", "DeliveryModel")
    Movement = apps.get_model("feed", "InventoryMovementModel")
    Production = apps.get_model("feed", "ProductionModel")
    RecipeItem = apps.get_model("feed", "RecipeItemModel")
    for delivery in Delivery.objects.select_related("ingredient"):
        if not delivery.quantity_kg:
            continue
        Movement.objects.create(
            farm_id=delivery.ingredient.farm_id,
            ingredient_id=delivery.ingredient_id,
            movement_type="DELIVERY",
            quantity_kg=abs(delivery.quantity_kg),
            unit_price=delivery.price_per_kg,
            source_model="feed.DeliveryModel",
            source_id=str(delivery.pk),
            note="Migracja istniejącej dostawy",
            movement_date=delivery.date,
        )
    for production in Production.objects.filter(status="COMPLETED").select_related("recipe"):
        custom = production.custom_recipe_data or {}
        quantities = {}
        for item in RecipeItem.objects.filter(recipe_id=production.recipe_id):
            percentage = Decimal(str(custom.get(str(item.ingredient_id), item.percentage)))
            quantity = (production.quantity_kg * percentage / Decimal("100")).quantize(Decimal("0.01"))
            quantities[item.ingredient_id] = quantities.get(item.ingredient_id, Decimal("0.00")) + quantity
        for ingredient_id, quantity in quantities.items():
            if quantity:
                Movement.objects.create(
                    farm_id=production.recipe.farm_id,
                    ingredient_id=ingredient_id,
                    movement_type="PRODUCTION_USAGE",
                    quantity_kg=-abs(quantity),
                    source_model="feed.ProductionModel",
                    source_id=str(production.pk),
                    note="Migracja istniejącej produkcji",
                    movement_date=production.date,
                )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("farms", "0005_auditlogmodel"),
        ("feed", "0003_ingredient_low_stock_threshold"),
    ]
    operations = [
        migrations.RunPython(assign_missing_farms, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ingredientmodel",
            name="farm",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ingredients", to="farms.farmmodel", verbose_name="Gospodarstwo"),
        ),
        migrations.AlterField(
            model_name="recipemodel",
            name="farm",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="recipes", to="farms.farmmodel", verbose_name="Gospodarstwo"),
        ),
        migrations.CreateModel(
            name="InventoryMovementModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("movement_type", models.CharField(choices=[("DELIVERY", "Dostawa"), ("PRODUCTION_USAGE", "Zużycie w produkcji"), ("ADJUSTMENT_POSITIVE", "Korekta dodatnia"), ("ADJUSTMENT_NEGATIVE", "Korekta ujemna"), ("REVERSAL", "Odwrócenie")], max_length=30)),
                ("quantity_kg", models.DecimalField(decimal_places=2, max_digits=12)),
                ("unit_price", models.DecimalField(blank=True, decimal_places=5, max_digits=14, null=True)),
                ("source_model", models.CharField(blank=True, max_length=100)),
                ("source_id", models.CharField(blank=True, max_length=100)),
                ("note", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("movement_date", models.DateField()),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inventory_movements", to=settings.AUTH_USER_MODEL)),
                ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_movements", to="farms.farmmodel")),
                ("ingredient", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="inventory_movements", to="feed.ingredientmodel")),
            ],
            options={"ordering": ("-movement_date", "-created_at", "-id")},
        ),
        migrations.AddConstraint(model_name="inventorymovementmodel", constraint=models.CheckConstraint(condition=~Q(quantity_kg=0), name="inventory_movement_quantity_nonzero")),
        migrations.AddConstraint(model_name="inventorymovementmodel", constraint=models.UniqueConstraint(condition=~Q(source_id=""), fields=("farm", "ingredient", "movement_type", "source_model", "source_id"), name="unique_inventory_source_movement")),
        migrations.AddIndex(model_name="inventorymovementmodel", index=models.Index(fields=["farm", "ingredient", "movement_date"], name="inventory_farm_ing_date_idx")),
        migrations.RunPython(build_initial_movements, migrations.RunPython.noop),
    ]
