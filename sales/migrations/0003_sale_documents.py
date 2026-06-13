import datetime
import decimal

from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_sales_to_rows(apps, schema_editor):
    PigSaleModel = apps.get_model('sales', 'PigSaleModel')
    SaleClassRowModel = apps.get_model('sales', 'SaleClassRowModel')

    for sale in PigSaleModel.objects.all():
        if SaleClassRowModel.objects.filter(sale_id=sale.pk).exists() or not sale.quantity:
            continue

        gross_value = (sale.total_weight or decimal.Decimal('0.00')) * (sale.price_per_kg or decimal.Decimal('0.00'))
        SaleClassRowModel.objects.create(
            sale_id=sale.pk,
            line_no=1,
            meat_class=sale.meat_class,
            quantity=sale.quantity,
            weight=sale.total_weight,
            price_per_kg=sale.price_per_kg,
            net_value=gross_value,
            vat_value=decimal.Decimal('0.00'),
            gross_value=gross_value,
        )
        sale.net_value = gross_value
        sale.vat_value = decimal.Decimal('0.00')
        sale.gross_value = gross_value
        sale.save(update_fields=['net_value', 'vat_value', 'gross_value'])


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_farm_scope'),
    ]

    operations = [
        migrations.AddField(
            model_name='pigsalemodel',
            name='avg_meatiness_seurop',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Średnia mięsność SEUROP (%)'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='dressing_percentage',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Wybój (%)'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='document_number',
            field=models.CharField(blank=True, max_length=50, verbose_name='Numer dokumentu'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='gross_value',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=12, verbose_name='Wartość brutto'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='live_weight',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Waga żywa (kg)'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='net_value',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=12, verbose_name='Wartość netto'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='no_settlement',
            field=models.BooleanField(default=False, verbose_name='Bez rozliczenia'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='slaughter_date',
            field=models.DateField(blank=True, null=True, verbose_name='Data uboju'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='supplier_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='Dostawca'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='tattoo',
            field=models.CharField(blank=True, max_length=50, verbose_name='Tatuaż'),
        ),
        migrations.AddField(
            model_name='pigsalemodel',
            name='vat_value',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=12, verbose_name='VAT'),
        ),
        migrations.AlterField(
            model_name='pigsalemodel',
            name='price_per_kg',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=8, verbose_name='Cena za kg (PLN)'),
        ),
        migrations.AlterField(
            model_name='pigsalemodel',
            name='quantity',
            field=models.PositiveIntegerField(default=0, verbose_name='Ilość sprzedanych sztuk'),
        ),
        migrations.AlterField(
            model_name='pigsalemodel',
            name='sale_date',
            field=models.DateField(blank=True, default=datetime.date.today, null=True, verbose_name='Data sprzedaży'),
        ),
        migrations.AlterField(
            model_name='pigsalemodel',
            name='total_weight',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0.00'), max_digits=10, verbose_name='Waga całkowita (kg)'),
        ),
        migrations.CreateModel(
            name='SaleClassRowModel',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line_no', models.PositiveIntegerField(verbose_name='Lp')),
                ('meat_class', models.CharField(blank=True, max_length=20, verbose_name='Klasa')),
                ('quantity', models.PositiveIntegerField(blank=True, null=True, verbose_name='Ilość')),
                ('weight', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Waga')),
                ('avg_weight', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Średnia waga')),
                ('avg_meatiness', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, verbose_name='Średnia mięsność')),
                ('price_per_kg', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, verbose_name='Cena')),
                ('net_value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Wartość')),
                ('vat_value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='VAT')),
                ('gross_value', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Wartość brutto')),
                ('sale', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rows', to='sales.pigsalemodel')),
            ],
            options={
                'verbose_name': 'Wiersz klasy sprzedaży',
                'verbose_name_plural': 'Wiersze klas sprzedaży',
                'ordering': ['line_no', 'id'],
            },
        ),
        migrations.RunPython(migrate_existing_sales_to_rows, migrations.RunPython.noop),
    ]
