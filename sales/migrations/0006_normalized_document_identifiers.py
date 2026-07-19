import django.db.models.functions.datetime
import django.db.models.functions.text
from django.db import migrations, models


def normalize_sale_identifiers(apps, schema_editor):
    Sale = apps.get_model('sales', 'PigSaleModel')
    used_documents = {}
    for sale in Sale.objects.order_by('farm_id', 'sale_date', 'id').iterator():
        base = sale.document_number.strip()
        candidate = base
        if base and sale.sale_date:
            scope = (sale.farm_id, sale.sale_date.year)
            used = used_documents.setdefault(scope, set())
            suffix_number = 0
            while candidate.lower() in used:
                suffix_number += 1
                suffix = f" ({suffix_number})"
                candidate = f"{base[:50 - len(suffix)].rstrip()}{suffix}"
            used.add(candidate.lower())
        if candidate != sale.document_number:
            Sale.objects.filter(pk=sale.pk).update(document_number=candidate)

    SaleRow = apps.get_model('sales', 'SaleClassRowModel')
    used_lines = {}
    next_lines = {}
    for row in SaleRow.objects.order_by('sale_id', 'id').iterator():
        used = used_lines.setdefault(row.sale_id, set())
        next_line = next_lines.setdefault(row.sale_id, 1)
        line_no = row.line_no
        if line_no in used:
            while next_line in used:
                next_line += 1
            line_no = next_line
            SaleRow.objects.filter(pk=row.pk).update(line_no=line_no)
        used.add(line_no)
        next_lines[row.sale_id] = max(next_line, line_no + 1)


class Migration(migrations.Migration):
    dependencies = [
        ('farms', '0014_default_automatic_feed_serving'),
        ('sales', '0005_require_farm'),
    ]

    operations = [
        migrations.RunPython(normalize_sale_identifiers, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='pigsalemodel',
            constraint=models.UniqueConstraint(
                models.F('farm'),
                django.db.models.functions.datetime.ExtractYear('sale_date'),
                django.db.models.functions.text.Lower(
                    django.db.models.functions.text.Trim('document_number')
                ),
                condition=models.Q(('document_number__gt', ''), ('sale_date__isnull', False)),
                name='unique_sale_document_per_farm_year_ci',
            ),
        ),
        migrations.AddConstraint(
            model_name='saleclassrowmodel',
            constraint=models.UniqueConstraint(
                fields=('sale', 'line_no'),
                name='unique_sale_line_number',
            ),
        ),
    ]
