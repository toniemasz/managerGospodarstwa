import django.core.validators
import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("farms", "0012_feed_serving_mode"),
        ("feed", "0006_recipe_versions"),
    ]
    operations = [
        migrations.AddField(model_name="productionmodel", name="completion_feed_serving_mode", field=models.CharField(blank=True, max_length=24)),
        migrations.CreateModel(name="FeedProductModel", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("name", models.CharField(max_length=150)), ("source_type", models.CharField(choices=[("PURCHASED_READY", "Kupiona pasza gotowa"), ("PRODUCED", "Pasza wytworzona")], max_length=24)),
            ("is_active", models.BooleanField(default=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_products", to="farms.farmmodel")),
            ("recipe", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name="feed_products", to="feed.recipemodel")),
        ], options={"constraints": [models.UniqueConstraint(fields=("farm", "name"), name="unique_feed_product_name_per_farm")]}),
        migrations.CreateModel(name="ReadyFeedDeliveryModel", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("date", models.DateField()),
            ("quantity_kg", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
            ("price_per_kg", models.DecimalField(decimal_places=5, max_digits=14, validators=[django.core.validators.MinValueValidator(Decimal("0.00001"))])),
            ("total_cost", models.DecimalField(decimal_places=2, max_digits=14)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ready_feed_deliveries", to="farms.farmmodel")),
            ("product", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="deliveries", to="feed.feedproductmodel")),
        ]),
        migrations.CreateModel(name="FinishedFeedBatchModel", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("batch_date", models.DateField()),
            ("initial_quantity_kg", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
            ("remaining_quantity_kg", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
            ("cost_per_kg", models.DecimalField(decimal_places=5, max_digits=14)), ("total_cost", models.DecimalField(decimal_places=2, max_digits=14)),
            ("cost_is_partial", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="finished_feed_batches", to="farms.farmmodel")),
            ("product", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="batches", to="feed.feedproductmodel")),
            ("production", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="finished_feed_batch", to="feed.productionmodel")),
            ("ready_feed_delivery", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="batch", to="feed.readyfeeddeliverymodel")),
        ], options={"constraints": [models.CheckConstraint(condition=models.Q(("initial_quantity_kg__gt", 0)), name="finished_batch_initial_positive"), models.CheckConstraint(condition=models.Q(("remaining_quantity_kg__gte", 0), ("remaining_quantity_kg__lte", models.F("initial_quantity_kg"))), name="finished_batch_remaining_range"), models.CheckConstraint(condition=models.Q(models.Q(("production__isnull", False), ("ready_feed_delivery__isnull", True)), models.Q(("production__isnull", True), ("ready_feed_delivery__isnull", False)), _connector="OR"), name="finished_batch_exactly_one_source")]}),
        migrations.CreateModel(name="FeedServingModel", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("date", models.DateField()), ("time", models.TimeField(blank=True, null=True)),
            ("quantity_kg", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
            ("note", models.CharField(blank=True, max_length=255)), ("total_cost", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
            ("is_automatic", models.BooleanField(default=False)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("automatic_for_production", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="automatic_feed_serving", to="feed.productionmodel")),
            ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ("farm", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feed_servings", to="farms.farmmodel")),
            ("product", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="servings", to="feed.feedproductmodel")),
        ]),
        migrations.CreateModel(name="FeedServingAllocationModel", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("quantity_kg", models.DecimalField(decimal_places=2, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0.01"))])),
            ("unit_cost", models.DecimalField(decimal_places=5, max_digits=14)), ("cost", models.DecimalField(decimal_places=2, max_digits=14)),
            ("batch", models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name="serving_allocations", to="feed.finishedfeedbatchmodel")),
            ("serving", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="feed.feedservingmodel")),
        ], options={"constraints": [models.UniqueConstraint(fields=("serving", "batch"), name="unique_serving_batch_allocation")]}),
    ]
