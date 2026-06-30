from __future__ import annotations

import hashlib
import json
from collections import Counter
from io import BytesIO, StringIO
from tempfile import NamedTemporaryFile
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, is_zipfile

from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.management import call_command
from django.db import transaction

from costs.models import CostCategoryModel, CostModel
from farms.models import FarmModel, FarmSettingsModel
from farms.services.settings_service import get_farm_settings
from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
)
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


BACKUP_FORMAT_VERSION = 1
MAX_UPLOAD_SIZE = 25 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024

USER_EXPORT_QUERYSETS = {
    'farms.FarmModel': lambda farm: FarmModel.objects.filter(id=farm.id),
    'farms.FarmSettingsModel': lambda farm: FarmSettingsModel.objects.filter(farm=farm),
    'sows.VaccinationPlanModel': lambda farm: VaccinationPlanModel.objects.filter(farm=farm).order_by('id'),
    'sows.SowModel': lambda farm: SowModel.objects.filter(farm=farm).order_by('id'),
    'sows.SowEventModel': lambda farm: SowEventModel.objects.filter(sow__farm=farm).order_by('id'),
    'feed.IngredientModel': lambda farm: IngredientModel.objects.filter(farm=farm).order_by('id'),
    'feed.DeliveryModel': lambda farm: DeliveryModel.objects.filter(ingredient__farm=farm).order_by('id'),
    'feed.IngredientPriceConfigModel': lambda farm: IngredientPriceConfigModel.objects.filter(ingredient__farm=farm).order_by('id'),
    'feed.RecipeModel': lambda farm: RecipeModel.objects.filter(farm=farm).order_by('id'),
    'feed.RecipeItemModel': lambda farm: RecipeItemModel.objects.filter(recipe__farm=farm).order_by('id'),
    'feed.ProductionModel': lambda farm: ProductionModel.objects.filter(recipe__farm=farm).order_by('id'),
    'sales.PigSaleModel': lambda farm: PigSaleModel.objects.filter(farm=farm).order_by('id'),
    'sales.SaleClassRowModel': lambda farm: SaleClassRowModel.objects.filter(sale__farm=farm).order_by('id'),
    'costs.CostCategoryModel': lambda farm: CostCategoryModel.objects.filter(farm=farm).order_by('id'),
    'costs.CostModel': lambda farm: CostModel.objects.filter(farm=farm).order_by('id'),
}

BUSINESS_MODELS = (
    VaccinationPlanModel,
    SowModel,
    SowEventModel,
    IngredientModel,
    DeliveryModel,
    IngredientPriceConfigModel,
    RecipeModel,
    RecipeItemModel,
    ProductionModel,
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


def restore_database_backup(uploaded_file) -> int:
    documents = _read_json_documents(uploaded_file)
    fixture_text, fixture = _select_database_fixture(documents)
    _verify_database_manifest(documents, fixture_text)
    _assert_database_can_be_restored(fixture)

    with transaction.atomic():
        FarmSettingsModel.objects.all().delete()
        FarmModel.objects.all().delete()
        with NamedTemporaryFile(mode='w', suffix='.json', encoding='utf-8') as fixture_file:
            fixture_file.write(fixture_text)
            fixture_file.flush()
            call_command('loaddata', fixture_file.name, verbosity=0)
    return len(fixture)


def import_user_backup(uploaded_file, farm: FarmModel) -> dict[str, int]:
    documents = _read_json_documents(uploaded_file)
    payload = _select_user_payload(documents)
    data = payload.get('data')
    if not isinstance(data, dict):
        raise BackupImportError('Plik nie zawiera danych gospodarstwa.')

    unknown_models = set(data) - set(USER_EXPORT_QUERYSETS)
    if unknown_models:
        raise BackupImportError(f'Plik zawiera nieobsługiwane modele: {", ".join(sorted(unknown_models))}.')

    _validate_user_records(data)
    existing = user_business_data_counts(farm)
    if existing:
        details = ', '.join(f'{label}: {count}' for label, count in existing.items())
        raise BackupImportError(
            f'Import zatrzymany: gospodarstwo ma już dane ({details}). '
            'Aby uniknąć duplikatów, nie zaimportowano żadnego rekordu.'
        )

    with transaction.atomic():
        counts = _restore_user_records(payload, data, farm)
        from feed.services.inventory_service import InventoryMovementService
        InventoryMovementService(farm).rebuild()
    return counts


def user_business_data_counts(farm: FarmModel) -> dict[str, int]:
    querysets = {
        'plany szczepień': VaccinationPlanModel.objects.filter(farm=farm),
        'maciory': SowModel.objects.filter(farm=farm),
        'zdarzenia macior': SowEventModel.objects.filter(sow__farm=farm),
        'składniki': IngredientModel.objects.filter(farm=farm),
        'dostawy': DeliveryModel.objects.filter(ingredient__farm=farm),
        'ceny składników': IngredientPriceConfigModel.objects.filter(ingredient__farm=farm),
        'receptury': RecipeModel.objects.filter(farm=farm),
        'pozycje receptur': RecipeItemModel.objects.filter(recipe__farm=farm),
        'produkcje': ProductionModel.objects.filter(recipe__farm=farm),
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
            'default_dashboard_period',
            'date_format',
            'visible_modules',
            'nav_modules',
            'dashboard_stats',
            'interface_scale',
        }
        for name in allowed_fields:
            if name in settings_records[0]['fields']:
                setattr(settings, name, settings_records[0]['fields'][name])
        settings.save()
        counts['ustawienia'] += 1

    plan_map = _create_farm_models(data, 'sows.VaccinationPlanModel', VaccinationPlanModel, farm, counts)
    sow_map = _create_farm_models(data, 'sows.SowModel', SowModel, farm, counts)
    ingredient_map = _create_farm_models(data, 'feed.IngredientModel', IngredientModel, farm, counts)
    recipe_map = _create_farm_models(data, 'feed.RecipeModel', RecipeModel, farm, counts)
    sale_map = _create_farm_models(data, 'sales.PigSaleModel', PigSaleModel, farm, counts)
    cost_category_map = _create_farm_models(data, 'costs.CostCategoryModel', CostCategoryModel, farm, counts)

    _create_related_models(data, 'sows.SowEventModel', SowEventModel, 'sow', sow_map, counts)
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

    for record in _records(data, 'feed.ProductionModel'):
        fields = _clean_fields(record['fields'], {'recipe'})
        custom_data = fields.get('custom_recipe_data')
        if isinstance(custom_data, dict):
            fields['custom_recipe_data'] = {
                str(_mapped(ingredient_map, old_id, 'składniki').pk): value
                for old_id, value in custom_data.items()
            }
        ProductionModel.objects.create(
            recipe=_mapped(recipe_map, record['fields'].get('recipe'), 'receptury'),
            **fields,
        )
        counts['produkcje'] += 1

    _create_related_models(data, 'sales.SaleClassRowModel', SaleClassRowModel, 'sale', sale_map, counts)
    for record in _records(data, 'costs.CostModel'):
        fields = _clean_fields(record['fields'], {'farm', 'category', 'created_by'})
        category_id = record['fields'].get('category')
        category = _mapped(cost_category_map, category_id, 'kategorie kosztów') if category_id else None
        created_at = fields.pop('created_at', None)
        updated_at = fields.pop('updated_at', None)
        obj = CostModel.objects.create(farm=farm, category=category, created_by=None, **fields)
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
        'sows.SowModel': 'maciory',
        'feed.IngredientModel': 'składniki',
        'feed.RecipeModel': 'receptury',
        'sales.PigSaleModel': 'sprzedaże',
        'costs.CostCategoryModel': 'kategorie kosztów',
    }.get(label)
    for record in _records(data, label):
        fields = _clean_fields(record['fields'], {'farm'})
        created_at = fields.pop('created_at', None)
        obj = model.objects.create(farm=farm, **fields)
        if created_at and hasattr(obj, 'created_at'):
            model.objects.filter(pk=obj.pk).update(created_at=created_at)
        result[str(record['pk'])] = obj
        if count_label:
            counts[count_label] += 1
    return result


def _create_related_models(data, label, model, relation_name, relation_map, counts):
    count_label = {
        'sows.SowEventModel': 'zdarzenia macior',
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
    return payloads[0]


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
