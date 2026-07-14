from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from collections import Counter
from io import BytesIO, StringIO
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, is_zipfile

from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import signing
from django.core.management import call_command
from django.db import transaction

from costs.models import CostCategoryModel, CostModel
from farms.models import BackupImportPreviewModel, FarmModel, FarmSettingsModel
from farms.services.settings_service import get_farm_settings
from feed.models import (
    DeliveryModel,
    FeedProductModel,
    FeedServingAllocationModel,
    FeedServingModel,
    FinishedFeedBatchModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    ReadyFeedDeliveryModel,
    RecipeItemModel,
    RecipeModel,
    RecipeVersionItemModel,
    RecipeVersionModel,
)
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import (
    MortalityReportModel,
    SowEventModel,
    SowModel,
    VaccinationCycleModel,
    VaccinationPlanModel,
)


BACKUP_FORMAT_VERSION = 4
SUPPORTED_USER_BACKUP_VERSIONS = {1, 2, 3, 4}


def _normalize_mortality_type(value):
    return {
        'sow': MortalityReportModel.TYPE_SOW,
        'post_weaning': MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
        None: MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
        '': MortalityReportModel.TYPE_UNSPECIFIED_POST_WEANING,
    }.get(value, value)
MAX_UPLOAD_SIZE = 25 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024

USER_EXPORT_QUERYSETS = {
    'farms.FarmModel': lambda farm: FarmModel.objects.filter(id=farm.id),
    'farms.FarmSettingsModel': lambda farm: FarmSettingsModel.objects.filter(farm=farm),
    'sows.VaccinationPlanModel': lambda farm: VaccinationPlanModel.objects.filter(farm=farm).order_by('id'),
    'sows.SowModel': lambda farm: SowModel.objects.filter(farm=farm).order_by('id'),
    'sows.SowEventModel': lambda farm: SowEventModel.objects.filter(sow__farm=farm).order_by('id'),
    'sows.VaccinationCycleModel': lambda farm: VaccinationCycleModel.objects.filter(plan__farm=farm).order_by('id'),
    'sows.MortalityReportModel': lambda farm: MortalityReportModel.objects.filter(farm=farm).order_by('id'),
    'feed.IngredientModel': lambda farm: IngredientModel.objects.filter(farm=farm).order_by('id'),
    'feed.DeliveryModel': lambda farm: DeliveryModel.objects.filter(ingredient__farm=farm).order_by('id'),
    'feed.IngredientPriceConfigModel': lambda farm: IngredientPriceConfigModel.objects.filter(ingredient__farm=farm).order_by('id'),
    'feed.RecipeModel': lambda farm: RecipeModel.objects.filter(farm=farm).order_by('id'),
    'feed.RecipeItemModel': lambda farm: RecipeItemModel.objects.filter(recipe__farm=farm).order_by('id'),
    'feed.RecipeVersionModel': lambda farm: RecipeVersionModel.objects.filter(recipe__farm=farm).order_by('id'),
    'feed.RecipeVersionItemModel': lambda farm: RecipeVersionItemModel.objects.filter(recipe_version__recipe__farm=farm).order_by('id'),
    'feed.ProductionModel': lambda farm: ProductionModel.objects.filter(recipe__farm=farm).order_by('id'),
    'feed.FeedProductModel': lambda farm: FeedProductModel.objects.filter(farm=farm).order_by('id'),
    'feed.ReadyFeedDeliveryModel': lambda farm: ReadyFeedDeliveryModel.objects.filter(farm=farm).order_by('id'),
    'feed.FinishedFeedBatchModel': lambda farm: FinishedFeedBatchModel.objects.filter(farm=farm).order_by('id'),
    'feed.FeedServingModel': lambda farm: FeedServingModel.objects.filter(farm=farm).order_by('id'),
    'feed.FeedServingAllocationModel': lambda farm: FeedServingAllocationModel.objects.filter(serving__farm=farm).order_by('id'),
    'sales.PigSaleModel': lambda farm: PigSaleModel.objects.filter(farm=farm).order_by('id'),
    'sales.SaleClassRowModel': lambda farm: SaleClassRowModel.objects.filter(sale__farm=farm).order_by('id'),
    'costs.CostCategoryModel': lambda farm: CostCategoryModel.objects.filter(farm=farm).order_by('id'),
    'costs.CostModel': lambda farm: CostModel.objects.filter(farm=farm).order_by('id'),
}

BUSINESS_MODELS = (
    VaccinationPlanModel,
    SowModel,
    SowEventModel,
    VaccinationCycleModel,
    MortalityReportModel,
    IngredientModel,
    DeliveryModel,
    IngredientPriceConfigModel,
    RecipeModel,
    RecipeItemModel,
    RecipeVersionModel,
    RecipeVersionItemModel,
    ProductionModel,
    FeedProductModel,
    ReadyFeedDeliveryModel,
    FinishedFeedBatchModel,
    FeedServingModel,
    FeedServingAllocationModel,
    PigSaleModel,
    SaleClassRowModel,
    CostCategoryModel,
    CostModel,
)


class BackupImportError(ValueError):
    pass


def build_user_backup(user, farm: FarmModel) -> tuple[bytes, str]:
    timestamp = _timestamp()
    json_filename = f'eksport_danych_{user.get_username()}_{timestamp}.json'
    zip_filename = f'eksport_danych_{user.get_username()}_{timestamp}.zip'
    data = {
        label: json.loads(serializers.serialize('json', queryset_factory(farm)))
        for label, queryset_factory in USER_EXPORT_QUERYSETS.items()
    }
    payload = {
        'format': 'managerGospodarstwa-user-backup',
        'version': BACKUP_FORMAT_VERSION,
        'generated_at': _timestamp(),
        'user': {
            'username': user.get_username(),
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        },
        'farm': {'id': farm.id, 'name': farm.name},
        'model_counts': {label: len(records) for label, records in data.items()},
        'data': data,
    }
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as export_zip:
        export_zip.writestr(json_filename, json.dumps(payload, ensure_ascii=False, indent=2))
    return zip_buffer.getvalue(), zip_filename


def build_database_backup() -> tuple[bytes, str]:
    json_buffer = StringIO()
    call_command(
        'dumpdata',
        stdout=json_buffer,
        indent=2,
        natural_foreign=True,
        natural_primary=True,
        exclude=[
            'contenttypes.ContentType',
            'auth.Permission',
            'admin.LogEntry',
            'sessions.Session',
            'farms.BackupImportPreviewModel',
        ],
    )
    fixture_text = json_buffer.getvalue()
    fixture = _parse_database_fixture(fixture_text)
    timestamp = _timestamp()
    json_filename = f'database_backup_{timestamp}.json'
    zip_filename = f'database_backup_{timestamp}.zip'
    manifest = {
        'format': 'managerGospodarstwa-database-backup',
        'version': BACKUP_FORMAT_VERSION,
        'data_file': json_filename,
        'sha256': hashlib.sha256(fixture_text.encode('utf-8')).hexdigest(),
        'record_count': len(fixture),
        'model_counts': dict(sorted(Counter(item['model'] for item in fixture).items())),
    }

    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, 'w', ZIP_DEFLATED) as backup_zip:
        backup_zip.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        backup_zip.writestr(json_filename, fixture_text)
    return zip_buffer.getvalue(), zip_filename


def store_database_backup_preview(uploaded_file, *, user):
    raw = uploaded_file.read()
    documents = _read_json_documents(SimpleUploadedFile(uploaded_file.name, raw))
    fixture_text, fixture = _select_database_fixture(documents)
    _verify_database_manifest(documents, fixture_text)
    model_counts = dict(sorted(Counter(item.get('model', 'nieznany') for item in fixture).items()))
    from django.utils import timezone
    from datetime import timedelta
    BackupImportPreviewModel.objects.filter(expires_at__lte=timezone.now()).delete()
    preview = BackupImportPreviewModel.objects.create(user=user, kind=BackupImportPreviewModel.Kinds.DATABASE, payload=raw, sha256=hashlib.sha256(raw).hexdigest(), expires_at=timezone.now() + timedelta(minutes=15))
    token = signing.dumps({'preview': preview.pk, 'user': user.pk}, salt='database-backup-preview')
    return token, {'record_count': len(fixture), 'model_counts': model_counts}


def load_database_backup_preview(token, *, user):
    try:
        signed = signing.loads(token, salt='database-backup-preview', max_age=15 * 60)
    except signing.BadSignature as error:
        raise BackupImportError('Podsumowanie kopii bazy wygasło. Prześlij plik ponownie.') from error
    if signed.get('user') != user.pk:
        raise BackupImportError('To podsumowanie należy do innego administratora.')
    from django.utils import timezone
    preview = BackupImportPreviewModel.objects.filter(pk=signed.get('preview'), user=user, kind=BackupImportPreviewModel.Kinds.DATABASE, expires_at__gt=timezone.now()).first()
    if preview is None:
        raise BackupImportError('Plik kopii bazy wygasł. Prześlij go ponownie.')
    raw = bytes(preview.payload)
    if hashlib.sha256(raw).hexdigest() != preview.sha256:
        raise BackupImportError('Plik kopii bazy jest uszkodzony.')
    return preview.pk, SimpleUploadedFile('database-backup.zip', raw)


def restore_database_backup(uploaded_file, *, replace=False) -> int:
    documents = _read_json_documents(uploaded_file)
    fixture_text, fixture = _select_database_fixture(documents)
    _verify_database_manifest(documents, fixture_text)
    if not replace:
        _assert_database_can_be_restored(fixture)

    with transaction.atomic():
        if replace:
            call_command('flush', interactive=False, reset_sequences=True, verbosity=0)
        else:
            FarmSettingsModel.objects.all().delete()
            FarmModel.objects.all().delete()
        with NamedTemporaryFile(mode='w', suffix='.json', encoding='utf-8') as fixture_file:
            fixture_file.write(fixture_text)
            fixture_file.flush()
            call_command('loaddata', fixture_file.name, verbosity=0)
    return len(fixture)


def analyze_user_backup(uploaded_file, farm: FarmModel) -> dict:
    documents = _read_json_documents(uploaded_file)
    payload = _select_user_payload(documents)
    data = payload.get('data')
    if not isinstance(data, dict):
        raise BackupImportError('Plik nie zawiera danych gospodarstwa.')
    unknown_models = set(data) - set(USER_EXPORT_QUERYSETS)
    if unknown_models:
        raise BackupImportError(f'Plik zawiera nieobsługiwane modele: {", ".join(sorted(unknown_models))}.')
    _validate_user_records(data)
    incoming = {label: len(records) for label, records in data.items() if records}
    current = user_business_data_counts(farm)
    existing_keys = {
        'sows.VaccinationPlanModel': set(VaccinationPlanModel.objects.filter(farm=farm).values_list('name', flat=True)),
        'sows.SowModel': set(SowModel.objects.filter(farm=farm).values_list('ear_tag', flat=True)),
        'feed.IngredientModel': set(IngredientModel.objects.filter(farm=farm).values_list('name', flat=True)),
        'feed.RecipeModel': set(RecipeModel.objects.filter(farm=farm).values_list('name', flat=True)),
        'feed.FeedProductModel': set(FeedProductModel.objects.filter(farm=farm).values_list('name', flat=True)),
        'sales.PigSaleModel': set(PigSaleModel.objects.filter(farm=farm).values_list('document_number', flat=True)),
        'costs.CostCategoryModel': set(CostCategoryModel.objects.filter(farm=farm).values_list('name', flat=True)),
    }
    key_fields = {'sows.VaccinationPlanModel': 'name', 'sows.SowModel': 'ear_tag', 'feed.IngredientModel': 'name', 'feed.RecipeModel': 'name', 'feed.FeedProductModel': 'name', 'sales.PigSaleModel': 'document_number', 'costs.CostCategoryModel': 'name'}
    merge_existing = 0
    for label, field in key_fields.items():
        normalized = {str(value).strip().casefold() for value in existing_keys[label] if value}
        merge_existing += sum(1 for record in _records(data, label) if str(record['fields'].get(field, '')).strip().casefold() in normalized)
    return {
        'payload': payload,
        'incoming': incoming,
        'incoming_total': sum(incoming.values()),
        'current': current,
        'current_total': sum(current.values()),
        'merge_new': max(0, sum(incoming.values()) - merge_existing),
        'merge_existing': merge_existing,
        'replace_remove': sum(current.values()),
        'replace_add': sum(incoming.values()),
        'farm_name': (payload.get('farm') or {}).get('name', ''),
        'generated_at': payload.get('generated_at', ''),
        'format_version': payload.get('version'),
    }


def store_user_backup_preview(uploaded_file, *, user, farm) -> tuple[str, dict]:
    raw = uploaded_file.read()
    if len(raw) > MAX_UPLOAD_SIZE:
        raise BackupImportError('Plik kopii jest zbyt duży.')
    analysis = analyze_user_backup(SimpleUploadedFile(uploaded_file.name, raw), farm)
    from django.utils import timezone
    from datetime import timedelta
    BackupImportPreviewModel.objects.filter(expires_at__lte=timezone.now()).delete()
    preview = BackupImportPreviewModel.objects.create(user=user, farm=farm, kind=BackupImportPreviewModel.Kinds.FARM, payload=raw, sha256=hashlib.sha256(raw).hexdigest(), expires_at=timezone.now() + timedelta(minutes=15))
    token = signing.dumps({'preview': preview.pk, 'user': user.pk, 'farm': farm.pk}, salt='farm-backup-preview')
    return token, analysis


def load_user_backup_preview(token, *, user, farm):
    try:
        signed = signing.loads(token, salt='farm-backup-preview', max_age=15 * 60)
    except signing.BadSignature as error:
        raise BackupImportError('Podsumowanie importu wygasło. Prześlij plik ponownie.') from error
    if signed.get('user') != user.pk or signed.get('farm') != farm.pk:
        raise BackupImportError('Podsumowanie importu nie należy do tego gospodarstwa.')
    from django.utils import timezone
    preview = BackupImportPreviewModel.objects.filter(pk=signed.get('preview'), user=user, farm=farm, kind=BackupImportPreviewModel.Kinds.FARM, expires_at__gt=timezone.now()).first()
    if preview is None:
        raise BackupImportError('Plik oczekujący na import wygasł. Prześlij go ponownie.')
    raw = bytes(preview.payload)
    if hashlib.sha256(raw).hexdigest() != preview.sha256:
        raise BackupImportError('Plik oczekujący na import jest uszkodzony.')
    return preview.pk, SimpleUploadedFile('backup.zip', raw)


def import_user_backup(uploaded_file, farm: FarmModel, *, mode=None) -> dict[str, int]:
    documents = _read_json_documents(uploaded_file)
    payload = _select_user_payload(documents)
    data = payload.get('data')
    if not isinstance(data, dict):
        raise BackupImportError('Plik nie zawiera danych gospodarstwa.')

    unknown_models = set(data) - set(USER_EXPORT_QUERYSETS)
    if unknown_models:
        raise BackupImportError(f'Plik zawiera nieobsługiwane modele: {", ".join(sorted(unknown_models))}.')

    _validate_user_records(data)
    if mode is None:
        existing = user_business_data_counts(farm)
        if existing:
            details = ', '.join(f'{label}: {count}' for label, count in existing.items())
            raise BackupImportError(f'Import zatrzymany: gospodarstwo ma już dane ({details}); nie zaimportowano żadnego rekordu.')
        mode = 'ADD_MISSING'
    with transaction.atomic():
        if mode == 'REPLACE_FARM':
            _delete_farm_business_data(farm)
        elif mode == 'ADD_MISSING' and user_business_data_counts(farm):
            return _merge_user_records(payload, data, farm)
        elif mode not in {'ADD_MISSING', 'REPLACE_FARM'}:
            raise BackupImportError('Nieprawidłowy tryb importu.')
        counts = _restore_user_records(payload, data, farm)
        from feed.actions.inventory import InventoryActions
        InventoryActions(farm).rebuild()
    return counts


def _delete_farm_business_data(farm):
    FeedServingModel.objects.filter(farm=farm).delete()
    FinishedFeedBatchModel.objects.filter(farm=farm).delete()
    ReadyFeedDeliveryModel.objects.filter(farm=farm).delete()
    FeedProductModel.objects.filter(farm=farm).delete()
    CostModel.objects.filter(farm=farm).delete()
    CostCategoryModel.objects.filter(farm=farm).delete()
    PigSaleModel.objects.filter(farm=farm).delete()
    ProductionModel.objects.filter(recipe__farm=farm).delete()
    RecipeModel.objects.filter(farm=farm).delete()
    DeliveryModel.objects.filter(ingredient__farm=farm).delete()
    IngredientPriceConfigModel.objects.filter(ingredient__farm=farm).delete()
    IngredientModel.objects.filter(farm=farm).delete()
    VaccinationCycleModel.objects.filter(plan__farm=farm).delete()
    MortalityReportModel.objects.filter(farm=farm).delete()
    SowModel.objects.filter(farm=farm).delete()
    VaccinationPlanModel.objects.filter(farm=farm).delete()


def _merge_user_records(payload, data, farm):
    """Bezpieczny merge: istniejące klucze biznesowe pozostają bez zmian."""
    counts = Counter()
    plan_map = {}
    for record in _records(data, 'sows.VaccinationPlanModel'):
        fields = _clean_fields(record['fields'], {'farm', 'selected_sows', 'excluded_sows'})
        plan, created = VaccinationPlanModel.objects.get_or_create(farm=farm, name__iexact=fields['name'], defaults=fields)
        plan_map[str(record['pk'])] = plan
        counts['plany szczepień'] += int(created)
    sow_map = {}
    for record in _records(data, 'sows.SowModel'):
        fields = _clean_fields(record['fields'], {'farm', 'created_at'})
        obj, created = SowModel.objects.get_or_create(farm=farm, ear_tag=fields.pop('ear_tag'), defaults=fields)
        sow_map[str(record['pk'])] = obj
        counts['maciory'] += int(created)
    for record in _records(data, 'sows.SowEventModel'):
        fields = _clean_fields(record['fields'], {'sow', 'created_at', 'vaccination_plan'})
        sow = _mapped(sow_map, record['fields'].get('sow'), 'maciory')
        plan_id = record['fields'].get('vaccination_plan')
        plan = _mapped(plan_map, plan_id, 'plany szczepień') if plan_id else None
        event, created = SowEventModel.objects.get_or_create(sow=sow, event_type=fields.pop('event_type'), event_date=fields.pop('event_date'), defaults=fields)
        counts['zdarzenia macior'] += int(created)
        if created and plan:
            event.vaccination_plan = plan
            event.save(update_fields=('vaccination_plan',))
    _restore_plan_sow_relations(data, plan_map, sow_map)
    for record in _records(data, 'sows.VaccinationCycleModel'):
        fields = _clean_fields(record['fields'], {'plan', 'sow', 'created_at'})
        plan = _mapped(plan_map, record['fields'].get('plan'), 'plany szczepień')
        sow = _mapped(sow_map, record['fields'].get('sow'), 'maciory')
        _, created = VaccinationCycleModel.objects.get_or_create(
            plan=plan,
            sow=sow,
            cycle_id=fields.pop('cycle_id'),
            defaults=fields,
        )
        counts['cykle szczepień'] += int(created)
    for record in _records(data, 'sows.MortalityReportModel'):
        fields = _clean_fields(record['fields'], {'farm', 'sow', 'created_by', 'created_at'})
        sow_id = record['fields'].get('sow')
        sow = _mapped(sow_map, sow_id, 'maciory') if sow_id else None
        _, created = MortalityReportModel.objects.get_or_create(
            farm=farm,
            sow=sow,
            mortality_type=_normalize_mortality_type(fields.pop('mortality_type', None)),
            mortality_date=fields.pop('mortality_date'),
            quantity=fields.pop('quantity'),
            defaults={**fields, 'created_by': None},
        )
        counts['upadki'] += int(created)
    ingredient_map = {}
    for record in _records(data, 'feed.IngredientModel'):
        fields = _clean_fields(record['fields'], {'farm', 'created_at'})
        obj, created = IngredientModel.objects.get_or_create(farm=farm, name__iexact=fields['name'], defaults=fields)
        ingredient_map[str(record['pk'])] = obj
        counts['składniki'] += int(created)
    recipe_map = {}
    for record in _records(data, 'feed.RecipeModel'):
        fields = _clean_fields(record['fields'], {'farm', 'created_at'})
        obj, created = RecipeModel.objects.get_or_create(farm=farm, name__iexact=fields['name'], defaults={'name': fields['name']})
        recipe_map[str(record['pk'])] = obj
        counts['receptury'] += int(created)
    for record in _records(data, 'feed.RecipeItemModel'):
        recipe = _mapped(recipe_map, record['fields'].get('recipe'), 'receptury')
        ingredient = _mapped(ingredient_map, record['fields'].get('ingredient'), 'składniki')
        _, created = RecipeItemModel.objects.get_or_create(recipe=recipe, ingredient=ingredient, defaults={'percentage': record['fields']['percentage']})
        counts['pozycje receptur'] += int(created)
    for record in _records(data, 'feed.DeliveryModel'):
        fields = _clean_fields(record['fields'], {'ingredient', 'remaining_quantity_kg'})
        ingredient = _mapped(ingredient_map, record['fields'].get('ingredient'), 'składniki')
        _, created = DeliveryModel.objects.get_or_create(ingredient=ingredient, date=fields['date'], quantity_kg=fields['quantity_kg'], price_per_kg=fields.get('price_per_kg'), defaults=fields)
        counts['dostawy'] += int(created)
    for record in _records(data, 'feed.IngredientPriceConfigModel'):
        fields = _clean_fields(record['fields'], {'ingredient'})
        _, created = IngredientPriceConfigModel.objects.get_or_create(ingredient=_mapped(ingredient_map, record['fields'].get('ingredient'), 'składniki'), defaults=fields)
        counts['ceny składników'] += int(created)
    product_map = {}
    for record in _records(data, 'feed.FeedProductModel'):
        fields = _clean_fields(record['fields'], {'farm', 'recipe', 'created_at'})
        recipe_id = record['fields'].get('recipe')
        obj, created = FeedProductModel.objects.get_or_create(
            farm=farm,
            name__iexact=fields['name'],
            defaults={**fields, 'recipe': _mapped(recipe_map, recipe_id, 'receptury') if recipe_id else None},
        )
        product_map[str(record['pk'])] = obj
        counts['produkty gotowej paszy'] += int(created)
    ready_delivery_map = {}
    for record in _records(data, 'feed.ReadyFeedDeliveryModel'):
        fields = _clean_fields(record['fields'], {'farm', 'product', 'created_by', 'created_at'})
        product = _mapped(product_map, record['fields'].get('product'), 'produkty gotowej paszy')
        obj, created = ReadyFeedDeliveryModel.objects.get_or_create(
            farm=farm, product=product, date=fields['date'], quantity_kg=fields['quantity_kg'], price_per_kg=fields['price_per_kg'],
            defaults={**fields, 'created_by': None},
        )
        ready_delivery_map[str(record['pk'])] = obj
        counts['dostawy gotowej paszy'] += int(created)
    for record in _records(data, 'feed.FinishedFeedBatchModel'):
        production_id = record['fields'].get('production')
        delivery_id = record['fields'].get('ready_feed_delivery')
        if production_id or not delivery_id:
            continue
        delivery = _mapped(ready_delivery_map, delivery_id, 'dostawy gotowej paszy')
        fields = _clean_fields(record['fields'], {'farm', 'product', 'production', 'ready_feed_delivery', 'created_at'})
        _, created = FinishedFeedBatchModel.objects.get_or_create(
            ready_feed_delivery=delivery,
            defaults={**fields, 'farm': farm, 'product': _mapped(product_map, record['fields'].get('product'), 'produkty gotowej paszy')},
        )
        counts['partie gotowej paszy'] += int(created)
    category_map = {}
    for record in _records(data, 'costs.CostCategoryModel'):
        fields = _clean_fields(record['fields'], {'farm', 'created_at', 'updated_at'})
        obj, created = CostCategoryModel.objects.get_or_create(farm=farm, name__iexact=fields['name'], defaults=fields)
        category_map[str(record['pk'])] = obj
        counts['kategorie kosztów'] += int(created)
    for record in _records(data, 'costs.CostModel'):
        production_id = record['fields'].get('production')
        if production_id:
            counts['pominięte rekordy wymagające pełnego odtworzenia'] += 1
            continue
        fields = _clean_fields(record['fields'], {'farm', 'category', 'production', 'created_by', 'created_at', 'updated_at'})
        category_id = record['fields'].get('category')
        category = _mapped(category_map, category_id, 'kategorie kosztów') if category_id else None
        _, created = CostModel.objects.get_or_create(
            farm=farm, date=fields['date'], amount=fields['amount'], document_number=fields.get('document_number', ''),
            defaults={**fields, 'category': category, 'created_by': None},
        )
        counts['koszty'] += int(created)
    # Modele o złożonej historii nie są zgadywane: istniejące dane pozostają,
    # a pełne odtworzenie jest dostępne przez świadomy tryb REPLACE_FARM.
    if any(_records(data, label) for label in ('feed.ProductionModel', 'feed.FeedServingModel', 'sales.PigSaleModel')):
        counts['pominięte rekordy wymagające pełnego odtworzenia'] += sum(len(_records(data, label)) for label in ('feed.ProductionModel', 'feed.FeedServingModel', 'sales.PigSaleModel'))
    return dict(counts)


def user_business_data_counts(farm: FarmModel) -> dict[str, int]:
    querysets = {
        'plany szczepień': VaccinationPlanModel.objects.filter(farm=farm),
        'maciory': SowModel.objects.filter(farm=farm),
        'zdarzenia macior': SowEventModel.objects.filter(sow__farm=farm),
        'cykle szczepień': VaccinationCycleModel.objects.filter(plan__farm=farm),
        'upadki': MortalityReportModel.objects.filter(farm=farm),
        'składniki': IngredientModel.objects.filter(farm=farm),
        'dostawy': DeliveryModel.objects.filter(ingredient__farm=farm),
        'ceny składników': IngredientPriceConfigModel.objects.filter(ingredient__farm=farm),
        'receptury': RecipeModel.objects.filter(farm=farm),
        'pozycje receptur': RecipeItemModel.objects.filter(recipe__farm=farm),
        'wersje receptur': RecipeVersionModel.objects.filter(recipe__farm=farm),
        'pozycje wersji receptur': RecipeVersionItemModel.objects.filter(recipe_version__recipe__farm=farm),
        'produkcje': ProductionModel.objects.filter(recipe__farm=farm),
        'produkty gotowej paszy': FeedProductModel.objects.filter(farm=farm),
        'dostawy gotowej paszy': ReadyFeedDeliveryModel.objects.filter(farm=farm),
        'partie gotowej paszy': FinishedFeedBatchModel.objects.filter(farm=farm),
        'podania paszy': FeedServingModel.objects.filter(farm=farm),
        'alokacje podań': FeedServingAllocationModel.objects.filter(serving__farm=farm),
        'sprzedaże': PigSaleModel.objects.filter(farm=farm),
        'wiersze sprzedaży': SaleClassRowModel.objects.filter(sale__farm=farm),
        'kategorie kosztów': CostCategoryModel.objects.filter(farm=farm),
        'koszty': CostModel.objects.filter(farm=farm),
    }
    return {label: queryset.count() for label, queryset in querysets.items() if queryset.exists()}


def _restore_user_records(payload, data, farm):
    counts = Counter()
    farm_data = payload.get('farm') or {}
    if isinstance(farm_data, dict) and farm_data.get('name'):
        farm.name = str(farm_data['name'])[:150]
        farm.save(update_fields=['name'])

    settings_records = _records(data, 'farms.FarmSettingsModel')
    if settings_records:
        settings = get_farm_settings(farm)
        allowed_fields = {
            'pregnancy_check_after_days',
            'gestation_days',
            'farrowing_alert_days_ahead',
            'vaccination_alert_days_ahead',
            'allow_farrowing_without_pregnancy_check',
            'ask_before_auto_pregnancy_check',
            'default_production_quantity_kg',
            'feed_serving_mode',
            'default_dashboard_period',
            'date_format',
            'visible_modules',
            'nav_modules',
            'dashboard_stats',
            'interface_scale',
            'theme',
            'font_scale',
        }
        for name in allowed_fields:
            if name in settings_records[0]['fields']:
                setattr(settings, name, settings_records[0]['fields'][name])
        settings.save()
        counts['ustawienia'] += 1

    plan_map = _create_farm_models(data, 'sows.VaccinationPlanModel', VaccinationPlanModel, farm, counts)
    sow_map = _create_farm_models(data, 'sows.SowModel', SowModel, farm, counts)
    _restore_plan_sow_relations(data, plan_map, sow_map)
    ingredient_map = _create_farm_models(data, 'feed.IngredientModel', IngredientModel, farm, counts)
    recipe_map = _create_farm_models(data, 'feed.RecipeModel', RecipeModel, farm, counts)
    sale_map = _create_farm_models(data, 'sales.PigSaleModel', PigSaleModel, farm, counts)
    cost_category_map = _create_farm_models(data, 'costs.CostCategoryModel', CostCategoryModel, farm, counts)

    product_map = {}
    for record in _records(data, 'feed.FeedProductModel'):
        fields = _clean_fields(record['fields'], {'farm', 'recipe'})
        created_at = fields.pop('created_at', None)
        recipe_id = record['fields'].get('recipe')
        obj = FeedProductModel.objects.create(
            farm=farm,
            recipe=_mapped(recipe_map, recipe_id, 'receptury') if recipe_id else None,
            **fields,
        )
        if created_at:
            FeedProductModel.objects.filter(pk=obj.pk).update(created_at=created_at)
        product_map[str(record['pk'])] = obj
        counts['produkty gotowej paszy'] += 1

    for record in _records(data, 'sows.SowEventModel'):
        fields = _clean_fields(record['fields'], {'sow', 'vaccination_plan', 'created_at'})
        plan_id = record['fields'].get('vaccination_plan')
        SowEventModel.objects.create(
            sow=_mapped(sow_map, record['fields'].get('sow'), 'zdarzenia macior'),
            vaccination_plan=_mapped(plan_map, plan_id, 'plany szczepień') if plan_id else None,
            **fields,
        )
        counts['zdarzenia macior'] += 1
    for record in _records(data, 'sows.VaccinationCycleModel'):
        fields = _clean_fields(record['fields'], {'plan', 'sow', 'created_at'})
        VaccinationCycleModel.objects.create(
            plan=_mapped(plan_map, record['fields'].get('plan'), 'plany szczepień'),
            sow=_mapped(sow_map, record['fields'].get('sow'), 'maciory'),
            **fields,
        )
        counts['cykle szczepień'] += 1
    for record in _records(data, 'sows.MortalityReportModel'):
        fields = _clean_fields(record['fields'], {'farm', 'sow', 'created_by', 'created_at'})
        fields['mortality_type'] = _normalize_mortality_type(fields.get('mortality_type'))
        sow_id = record['fields'].get('sow')
        MortalityReportModel.objects.create(
            farm=farm,
            sow=_mapped(sow_map, sow_id, 'maciory') if sow_id else None,
            created_by=None,
            **fields,
        )
        counts['upadki'] += 1
    _create_related_models(data, 'feed.DeliveryModel', DeliveryModel, 'ingredient', ingredient_map, counts)
    _create_related_models(
        data,
        'feed.IngredientPriceConfigModel',
        IngredientPriceConfigModel,
        'ingredient',
        ingredient_map,
        counts,
    )

    for record in _records(data, 'feed.RecipeItemModel'):
        fields = _clean_fields(record['fields'], {'recipe', 'ingredient'})
        RecipeItemModel.objects.create(
            recipe=_mapped(recipe_map, record['fields'].get('recipe'), 'receptury'),
            ingredient=_mapped(ingredient_map, record['fields'].get('ingredient'), 'składniki'),
            **fields,
        )
        counts['pozycje receptur'] += 1

    version_map = {}
    for record in _records(data, 'feed.RecipeVersionModel'):
        fields = _clean_fields(record['fields'], {'recipe', 'created_by'})
        fields.pop('created_at', None)
        obj = RecipeVersionModel.objects.create(
            recipe=_mapped(recipe_map, record['fields'].get('recipe'), 'receptury'),
            created_by=None,
            **fields,
        )
        version_map[str(record['pk'])] = obj
        counts['wersje receptur'] += 1
    for record in _records(data, 'feed.RecipeVersionItemModel'):
        fields = _clean_fields(record['fields'], {'recipe_version', 'ingredient'})
        RecipeVersionItemModel.objects.create(
            recipe_version=_mapped(version_map, record['fields'].get('recipe_version'), 'wersje receptur'),
            ingredient=_mapped(ingredient_map, record['fields'].get('ingredient'), 'składniki'),
            **fields,
        )
        counts['pozycje wersji receptur'] += 1

    production_map = {}
    for record in _records(data, 'feed.ProductionModel'):
        fields = _clean_fields(record['fields'], {'recipe', 'recipe_version'})
        historical = {
            name: fields.pop(name)
            for name in (
                'status', 'completed_at', 'feed_cost_total', 'feed_cost_per_kg',
                'feed_cost_is_partial', 'feed_cost_note', 'completion_feed_serving_mode',
            )
            if name in fields
        }
        fields.pop('created_at', None)
        custom_data = fields.get('custom_recipe_data')
        if isinstance(custom_data, dict):
            fields['custom_recipe_data'] = {
                str(_mapped(ingredient_map, old_id, 'składniki').pk): value
                for old_id, value in custom_data.items()
            }
        version_id = record['fields'].get('recipe_version')
        obj = ProductionModel.objects.create(
            recipe=_mapped(recipe_map, record['fields'].get('recipe'), 'receptury'),
            recipe_version=_mapped(version_map, version_id, 'wersje receptur') if version_id else None,
            status=ProductionModel.Statuses.QUEUED,
            **fields,
        )
        if historical:
            ProductionModel.objects.filter(pk=obj.pk).update(**historical)
            for name, value in historical.items():
                setattr(obj, name, value)
        production_map[str(record['pk'])] = obj
        counts['produkcje'] += 1

    ready_delivery_map = {}
    for record in _records(data, 'feed.ReadyFeedDeliveryModel'):
        fields = _clean_fields(record['fields'], {'farm', 'product', 'created_by'})
        fields.pop('created_at', None)
        obj = ReadyFeedDeliveryModel.objects.create(
            farm=farm,
            product=_mapped(product_map, record['fields'].get('product'), 'produkty gotowej paszy'),
            created_by=None,
            **fields,
        )
        ready_delivery_map[str(record['pk'])] = obj
        counts['dostawy gotowej paszy'] += 1

    batch_map = {}
    for record in _records(data, 'feed.FinishedFeedBatchModel'):
        fields = _clean_fields(record['fields'], {'farm', 'product', 'production', 'ready_feed_delivery'})
        fields.pop('created_at', None)
        production_id = record['fields'].get('production')
        delivery_id = record['fields'].get('ready_feed_delivery')
        obj, _ = FinishedFeedBatchModel.objects.update_or_create(
            production=_mapped(production_map, production_id, 'produkcje') if production_id else None,
            ready_feed_delivery=_mapped(ready_delivery_map, delivery_id, 'dostawy gotowej paszy') if delivery_id else None,
            defaults={
                'farm': farm,
                'product': _mapped(product_map, record['fields'].get('product'), 'produkty gotowej paszy'),
                **fields,
            },
        )
        batch_map[str(record['pk'])] = obj
        counts['partie gotowej paszy'] += 1

    serving_map = {}
    for record in _records(data, 'feed.FeedServingModel'):
        fields = _clean_fields(record['fields'], {'farm', 'product', 'automatic_for_production', 'created_by'})
        fields.pop('created_at', None)
        production_id = record['fields'].get('automatic_for_production')
        obj = FeedServingModel.objects.create(
            farm=farm,
            product=_mapped(product_map, record['fields'].get('product'), 'produkty gotowej paszy'),
            automatic_for_production=_mapped(production_map, production_id, 'produkcje') if production_id else None,
            created_by=None,
            **fields,
        )
        serving_map[str(record['pk'])] = obj
        counts['podania paszy'] += 1

    for record in _records(data, 'feed.FeedServingAllocationModel'):
        fields = _clean_fields(record['fields'], {'serving', 'batch'})
        FeedServingAllocationModel.objects.create(
            serving=_mapped(serving_map, record['fields'].get('serving'), 'podania paszy'),
            batch=_mapped(batch_map, record['fields'].get('batch'), 'partie gotowej paszy'),
            **fields,
        )
        counts['alokacje podań'] += 1

    _create_related_models(data, 'sales.SaleClassRowModel', SaleClassRowModel, 'sale', sale_map, counts)
    for record in _records(data, 'costs.CostModel'):
        fields = _clean_fields(record['fields'], {'farm', 'category', 'production', 'created_by'})
        category_id = record['fields'].get('category')
        category = _mapped(cost_category_map, category_id, 'kategorie kosztów') if category_id else None
        production_id = record['fields'].get('production')
        created_at = fields.pop('created_at', None)
        updated_at = fields.pop('updated_at', None)
        obj = CostModel.objects.create(
            farm=farm,
            category=category,
            production=_mapped(production_map, production_id, 'produkcje') if production_id else None,
            created_by=None,
            **fields,
        )
        timestamp_values = {}
        if created_at:
            timestamp_values['created_at'] = created_at
        if updated_at:
            timestamp_values['updated_at'] = updated_at
        if timestamp_values:
            CostModel.objects.filter(pk=obj.pk).update(**timestamp_values)
        counts['koszty'] += 1
    counts['plany szczepień'] += len(plan_map)
    return dict(counts)


def _create_farm_models(data, label, model, farm, counts):
    result = {}
    count_label = {
        'sows.VaccinationPlanModel': 'plany szczepień',
        'sows.SowModel': 'maciory',
        'feed.IngredientModel': 'składniki',
        'feed.RecipeModel': 'receptury',
        'sales.PigSaleModel': 'sprzedaże',
        'costs.CostCategoryModel': 'kategorie kosztów',
    }.get(label)
    for record in _records(data, label):
        many_to_many_fields = {field.name for field in model._meta.many_to_many}
        fields = _clean_fields(record['fields'], {'farm', *many_to_many_fields})
        created_at = fields.pop('created_at', None)
        obj = model.objects.create(farm=farm, **fields)
        if created_at and hasattr(obj, 'created_at'):
            model.objects.filter(pk=obj.pk).update(created_at=created_at)
        result[str(record['pk'])] = obj
        if count_label:
            counts[count_label] += 1
    return result


def _restore_plan_sow_relations(data, plan_map, sow_map):
    for record in _records(data, 'sows.VaccinationPlanModel'):
        plan = _mapped(plan_map, record['pk'], 'plany szczepień')
        for field_name in ('selected_sows', 'excluded_sows'):
            sow_ids = record['fields'].get(field_name) or []
            getattr(plan, field_name).add(*[
                _mapped(sow_map, sow_id, 'maciory')
                for sow_id in sow_ids
            ])


def _create_related_models(data, label, model, relation_name, relation_map, counts):
    count_label = {
        'sows.SowEventModel': 'zdarzenia macior',
        'sows.VaccinationCycleModel': 'cykle szczepień',
        'feed.DeliveryModel': 'dostawy',
        'feed.IngredientPriceConfigModel': 'ceny składników',
        'sales.SaleClassRowModel': 'wiersze sprzedaży',
    }[label]
    for record in _records(data, label):
        fields = _clean_fields(record['fields'], {relation_name})
        model.objects.create(
            **{relation_name: _mapped(relation_map, record['fields'].get(relation_name), count_label)},
            **fields,
        )
        counts[count_label] += 1


def _validate_user_records(data):
    for label, records in data.items():
        if not isinstance(records, list):
            raise BackupImportError(f'Nieprawidłowa lista rekordów: {label}.')
        seen_pks = set()
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get('fields'), dict) or 'pk' not in record:
                raise BackupImportError(f'Nieprawidłowy rekord w sekcji {label}.')
            pk = str(record['pk'])
            if pk in seen_pks:
                raise BackupImportError(
                    f'Import zatrzymany: duplikat identyfikatora {record["pk"]} w sekcji {label}.'
                )
            seen_pks.add(pk)

    unique_names = {
        'sows.VaccinationPlanModel': 'name',
        'sows.SowModel': 'ear_tag',
        'feed.IngredientModel': 'name',
        'feed.RecipeModel': 'name',
        'sales.PigSaleModel': 'document_number',
        'costs.CostCategoryModel': 'name',
    }
    for label, field_name in unique_names.items():
        values = [str(record['fields'].get(field_name, '')).strip().casefold() for record in _records(data, label)]
        duplicates = sorted(value for value, count in Counter(values).items() if value and count > 1)
        if duplicates:
            raise BackupImportError(
                f'Import zatrzymany: duplikaty w sekcji {label}: {", ".join(duplicates)}.'
            )

    required_fields = {
        'sows.SowModel': {'ear_tag'},
        'sows.SowEventModel': {'sow', 'event_type', 'event_date'},
        'sows.VaccinationCycleModel': {'plan', 'sow', 'cycle_id', 'scheduled_date', 'status'},
        'sows.MortalityReportModel': {'mortality_date', 'quantity'},
        'feed.IngredientModel': {'name'},
        'feed.DeliveryModel': {'ingredient', 'date', 'quantity_kg'},
        'feed.RecipeModel': {'name'},
        'feed.RecipeItemModel': {'recipe', 'ingredient', 'percentage'},
        'feed.ProductionModel': {'recipe', 'date', 'quantity_kg'},
        'costs.CostModel': {'date', 'amount', 'description'},
    }
    for label, names in required_fields.items():
        for record in _records(data, label):
            missing = sorted(name for name in names if record['fields'].get(name) in (None, ''))
            if missing:
                raise BackupImportError(
                    f'Import zatrzymany: rekord {label}#{record["pk"]} nie ma wymaganych pól: '
                    f'{", ".join(missing)}.'
                )


def _assert_database_can_be_restored(fixture):
    existing = {model._meta.verbose_name_plural: model.objects.count() for model in BUSINESS_MODELS if model.objects.exists()}
    if existing:
        details = ', '.join(f'{label}: {count}' for label, count in existing.items())
        raise BackupImportError(
            f'Przywracanie zatrzymane: baza ma już dane biznesowe ({details}). '
            'Nie zaimportowano żadnego rekordu.'
        )

    UserModel = get_user_model()
    seen_usernames = set()
    for item in fixture:
        if item.get('model') != UserModel._meta.label_lower:
            continue
        username = str(item.get('fields', {}).get(UserModel.USERNAME_FIELD, '')).strip()
        if not username:
            raise BackupImportError('Kopia zawiera użytkownika bez nazwy.')
        if username.casefold() in seen_usernames:
            raise BackupImportError(f'Kopia zawiera zduplikowanego użytkownika: {username}.')
        seen_usernames.add(username.casefold())
        existing_user = UserModel.objects.filter(**{UserModel.USERNAME_FIELD: username}).first()
        fixture_pk = item.get('pk')
        if existing_user and fixture_pk is not None and existing_user.pk != fixture_pk:
            raise BackupImportError(
                f'Konflikt użytkownika {username}: istniejące konto ma inny identyfikator. Import przerwany.'
            )


def _read_json_documents(uploaded_file):
    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > MAX_UPLOAD_SIZE:
        raise BackupImportError('Plik kopii jest zbyt duży.')
    raw = uploaded_file.read()
    if len(raw) > MAX_UPLOAD_SIZE:
        raise BackupImportError('Plik kopii jest zbyt duży.')

    documents = {}
    buffer = BytesIO(raw)
    if is_zipfile(buffer):
        try:
            with ZipFile(buffer) as archive:
                json_files = [item for item in archive.infolist() if not item.is_dir() and item.filename.lower().endswith('.json')]
                if not json_files:
                    raise BackupImportError('Archiwum nie zawiera pliku JSON.')
                if sum(item.file_size for item in json_files) > MAX_UNCOMPRESSED_SIZE:
                    raise BackupImportError('Rozpakowana kopia jest zbyt duża.')
                for item in json_files:
                    documents[item.filename] = _decode_json(archive.read(item), item.filename)
        except BadZipFile as error:
            raise BackupImportError('Archiwum ZIP jest uszkodzone.') from error
    else:
        documents[getattr(uploaded_file, 'name', 'backup.json')] = _decode_json(raw, 'backup.json')
    return documents


def _decode_json(raw, filename):
    try:
        text = raw.decode('utf-8-sig')
        return text, json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupImportError(f'Plik {filename} nie jest prawidłowym JSON-em.') from error


def _select_database_fixture(documents):
    fixtures = [(text, value) for text, value in documents.values() if isinstance(value, list)]
    if len(fixtures) != 1:
        raise BackupImportError('Kopia bazy musi zawierać dokładnie jeden plik danych JSON.')
    return fixtures[0][0], _parse_database_fixture(fixtures[0][0])


def _parse_database_fixture(text):
    try:
        fixture = json.loads(text)
    except json.JSONDecodeError as error:
        raise BackupImportError('Kopia bazy zawiera nieprawidłowy JSON.') from error
    if not isinstance(fixture, list):
        raise BackupImportError('Kopia bazy ma nieprawidłowy format.')
    seen_primary_keys = set()
    for item in fixture:
        if not isinstance(item, dict) or not isinstance(item.get('model'), str) or not isinstance(item.get('fields'), dict):
            raise BackupImportError('Kopia bazy zawiera nieprawidłowy rekord.')
        if item.get('pk') is not None:
            identity = (item['model'], str(item['pk']))
            if identity in seen_primary_keys:
                raise BackupImportError(
                    f'Kopia bazy zawiera duplikat rekordu {item["model"]} o ID {item["pk"]}.'
                )
            seen_primary_keys.add(identity)
    return fixture


def _select_user_payload(documents):
    payloads = [value for _, value in documents.values() if isinstance(value, dict) and isinstance(value.get('data'), dict)]
    if len(payloads) != 1:
        raise BackupImportError('Kopia użytkownika musi zawierać dokładnie jeden zestaw danych gospodarstwa.')
    return _upgrade_user_payload(payloads[0])


def _upgrade_user_payload(payload):
    upgraded = deepcopy(payload)
    raw_version = upgraded.get('version', 1)
    try:
        version = int(raw_version)
    except (TypeError, ValueError) as error:
        raise BackupImportError('Kopia gospodarstwa ma nieprawidłowy numer wersji.') from error
    if version not in SUPPORTED_USER_BACKUP_VERSIONS:
        raise BackupImportError(
            f'Nieobsługiwana wersja kopii gospodarstwa: {version}. '
            f'Obsługiwane wersje: {sorted(SUPPORTED_USER_BACKUP_VERSIONS)}.'
        )
    data = upgraded.setdefault('data', {})
    for label in USER_EXPORT_QUERYSETS:
        data.setdefault(label, [])
    upgraded['source_version'] = version
    upgraded['version'] = BACKUP_FORMAT_VERSION
    return upgraded


def _verify_database_manifest(documents, fixture_text):
    manifests = [value for _, value in documents.values() if isinstance(value, dict) and value.get('format') == 'managerGospodarstwa-database-backup']
    if not manifests:
        return
    manifest = manifests[0]
    expected = manifest.get('sha256')
    actual = hashlib.sha256(fixture_text.encode('utf-8')).hexdigest()
    if expected and expected != actual:
        raise BackupImportError('Suma kontrolna kopii jest nieprawidłowa. Plik mógł zostać uszkodzony.')


def _records(data, label):
    return data.get(label, [])


def _clean_fields(fields, excluded):
    return {
        name: value
        for name, value in fields.items()
        if name not in excluded and name not in {'id', 'pk'}
    }


def _mapped(mapping, old_id, label):
    try:
        return mapping[str(old_id)]
    except KeyError as error:
        raise BackupImportError(f'Brak powiązanego rekordu ({label}, ID {old_id}).') from error


def _timestamp():
    from django.utils import timezone

    return timezone.now().strftime('%Y-%m-%d_%H-%M-%S')
