import copy
import json
from datetime import date, time
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from farms.models import AuditLogModel
from farms.services.data_backup import (
    BackupImportError,
    build_database_backup,
    build_user_backup,
    analyze_user_backup,
    import_user_backup,
    restore_database_backup,
)
from farms.services.farm_service import get_or_create_user_farm
from farms.services.settings_service import get_farm_settings
from feed.models import (
    DeliveryModel,
    IngredientModel,
    IngredientPriceConfigModel,
    ProductionModel,
    RecipeItemModel,
    RecipeModel,
    FeedProductModel,
    FinishedFeedBatchModel,
    ReadyFeedDeliveryModel,
)
from sales.models import PigSaleModel, SaleClassRowModel
from sows.models import SowEventModel, SowModel, VaccinationPlanModel


def _user_backup_fixture(user, farm):
    archive, _ = build_user_backup(user, farm)
    return SimpleUploadedFile('backup.zip', archive, content_type='application/zip')


def _payload_from_archive(archive):
    with ZipFile(BytesIO(archive)) as backup_zip:
        data_file = next(name for name in backup_zip.namelist() if name != 'manifest.json')
        return json.loads(backup_zip.read(data_file))


def _create_complete_farm_data(farm):
    settings = get_farm_settings(farm)
    settings.gestation_days = 116
    settings.save(update_fields=['gestation_days'])

    VaccinationPlanModel.objects.create(farm=farm, name='Parwo', reminder_days_ahead=5)
    sow = SowModel.objects.create(farm=farm, ear_tag='SOW-BACKUP', entry_date=date(2025, 1, 1))
    SowEventModel.objects.create(
        sow=sow,
        event_type='FARROWING',
        event_date=date(2025, 5, 1),
        details={'born_alive': 12, 'born_dead': 1},
    )

    ingredient = IngredientModel.objects.create(
        farm=farm,
        name='Pszenica',
        low_stock_threshold_kg=Decimal('750.00'),
    )
    DeliveryModel.objects.create(
        ingredient=ingredient,
        date=date(2025, 2, 1),
        quantity_kg=Decimal('5000.00'),
        price_per_kg=Decimal('1.25'),
    )
    IngredientPriceConfigModel.objects.create(ingredient=ingredient, price_per_kg=Decimal('1.30'))
    recipe = RecipeModel.objects.create(farm=farm, name='Starter')
    RecipeItemModel.objects.create(recipe=recipe, ingredient=ingredient, percentage=Decimal('100.00'))
    ProductionModel.objects.create(
        recipe=recipe,
        date=date(2025, 3, 1),
        time=time(8, 30),
        quantity_kg=Decimal('2000.00'),
        custom_recipe_data={str(ingredient.pk): '100.00'},
    )

    sale = PigSaleModel.objects.create(
        farm=farm,
        sale_date=date(2025, 6, 1),
        document_number='FV/BACKUP/1',
        quantity=10,
        total_weight=Decimal('1000.00'),
        price_per_kg=Decimal('8.00'),
        net_value=Decimal('8000.00'),
        gross_value=Decimal('8640.00'),
    )
    SaleClassRowModel.objects.create(
        sale=sale,
        line_no=1,
        meat_class='E',
        quantity=10,
        weight=Decimal('1000.00'),
        net_value=Decimal('8000.00'),
        gross_value=Decimal('8640.00'),
    )


@pytest.mark.django_db
def test_user_backup_restores_all_models_and_relationships():
    source_user = User.objects.create_user(username='backup-source')
    source_farm = get_or_create_user_farm(source_user)
    source_farm.name = 'Odtworzone gospodarstwo'
    source_farm.save(update_fields=['name'])
    _create_complete_farm_data(source_farm)
    backup_file = _user_backup_fixture(source_user, source_farm)

    target_user = User.objects.create_user(username='backup-target')
    target_farm = get_or_create_user_farm(target_user)
    get_farm_settings(target_farm)

    counts = import_user_backup(backup_file, target_farm)

    target_farm.refresh_from_db()
    assert target_farm.name == 'Odtworzone gospodarstwo'
    assert get_farm_settings(target_farm).gestation_days == 116
    assert counts['maciory'] == 1
    assert counts['zdarzenia macior'] == 1
    assert counts['składniki'] == 1
    assert counts['receptury'] == 1
    assert counts['produkcje'] == 1
    assert counts['sprzedaże'] == 1
    assert SowEventModel.objects.get(sow__farm=target_farm).sow.ear_tag == 'SOW-BACKUP'
    restored_item = RecipeItemModel.objects.get(recipe__farm=target_farm)
    assert restored_item.ingredient.farm == target_farm
    restored_production = ProductionModel.objects.get(recipe__farm=target_farm)
    assert list(restored_production.custom_recipe_data) == [str(restored_item.ingredient_id)]
    assert SaleClassRowModel.objects.get(sale__farm=target_farm).sale.document_number == 'FV/BACKUP/1'


@pytest.mark.django_db
def test_user_backup_refuses_existing_data_without_partial_import():
    source_user = User.objects.create_user(username='existing-source')
    source_farm = get_or_create_user_farm(source_user)
    SowModel.objects.create(farm=source_farm, ear_tag='SOURCE')
    backup_file = _user_backup_fixture(source_user, source_farm)

    target_user = User.objects.create_user(username='existing-target')
    target_farm = get_or_create_user_farm(target_user)
    SowModel.objects.create(farm=target_farm, ear_tag='EXISTING')

    with pytest.raises(BackupImportError, match='ma już dane'):
        import_user_backup(backup_file, target_farm)

    assert list(SowModel.objects.filter(farm=target_farm).values_list('ear_tag', flat=True)) == ['EXISTING']


@pytest.mark.django_db
def test_user_backup_refuses_duplicates_inside_file():
    source_user = User.objects.create_user(username='duplicate-source')
    source_farm = get_or_create_user_farm(source_user)
    IngredientModel.objects.create(farm=source_farm, name='Jęczmień')
    archive, _ = build_user_backup(source_user, source_farm)
    payload = _payload_from_archive(archive)
    duplicate = copy.deepcopy(payload['data']['feed.IngredientModel'][0])
    duplicate['pk'] += 1000
    payload['data']['feed.IngredientModel'].append(duplicate)
    backup_file = SimpleUploadedFile(
        'duplicate.json',
        json.dumps(payload).encode(),
        content_type='application/json',
    )
    target_user = User.objects.create_user(username='duplicate-target')
    target_farm = get_or_create_user_farm(target_user)

    with pytest.raises(BackupImportError, match='duplikaty'):
        import_user_backup(backup_file, target_farm)

    assert not IngredientModel.objects.filter(farm=target_farm).exists()


@pytest.mark.django_db(transaction=True)
def test_database_backup_contains_manifest_and_can_restore_business_data():
    user = User.objects.create_user(username='database-backup-user')
    farm = get_or_create_user_farm(user)
    SowModel.objects.create(farm=farm, ear_tag='DB-BACKUP')
    archive, filename = build_database_backup()

    with ZipFile(BytesIO(archive)) as backup_zip:
        manifest = json.loads(backup_zip.read('manifest.json'))
    assert filename.endswith('.zip')
    assert manifest['format'] == 'managerGospodarstwa-database-backup'
    assert manifest['model_counts']['sows.sowmodel'] == 1

    SowModel.objects.all().delete()
    get_farm_settings(farm).delete()
    farm.delete()
    restored = restore_database_backup(
        SimpleUploadedFile('database.zip', archive, content_type='application/zip')
    )

    assert restored == manifest['record_count']
    assert SowModel.objects.get(ear_tag='DB-BACKUP').farm.owner.username == 'database-backup-user'


@pytest.mark.django_db
def test_database_restore_refuses_non_empty_database():
    user = User.objects.create_user(username='database-existing')
    farm = get_or_create_user_farm(user)
    SowModel.objects.create(farm=farm, ear_tag='EXISTING')
    archive, _ = build_database_backup()

    with pytest.raises(BackupImportError, match='baza ma już dane biznesowe'):
        restore_database_backup(SimpleUploadedFile('database.zip', archive))

    assert SowModel.objects.filter(ear_tag='EXISTING').count() == 1


@pytest.mark.django_db
def test_settings_import_view_reports_duplicate_block(client):
    source_user = User.objects.create_user(username='view-source')
    source_farm = get_or_create_user_farm(source_user)
    SowModel.objects.create(farm=source_farm, ear_tag='SOURCE')
    backup_file = _user_backup_fixture(source_user, source_farm)

    target_user = User.objects.create_user(username='view-target', password='password')
    target_farm = get_or_create_user_farm(target_user)
    SowModel.objects.create(farm=target_farm, ear_tag='EXISTING')
    client.login(username='view-target', password='password')

    response = client.post(reverse('farm_settings'), {
        'import_backup': '1',
        'confirm_empty_import': 'on',
        'backup_file': backup_file,
    })

    assert response.status_code == 302
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    assert any('Import zatrzymany' in message and 'nie zaimportowano' in message for message in messages)
    assert list(SowModel.objects.filter(farm=target_farm).values_list('ear_tag', flat=True)) == ['EXISTING']


@pytest.mark.django_db
def test_settings_import_view_restores_user_backup_into_empty_farm(client):
    source_user = User.objects.create_user(username='view-empty-source')
    source_farm = get_or_create_user_farm(source_user)
    source_farm.name = 'Importowane gospodarstwo'
    source_farm.save(update_fields=['name'])
    _create_complete_farm_data(source_farm)
    backup_file = _user_backup_fixture(source_user, source_farm)

    target_user = User.objects.create_user(username='view-empty-target', password='password')
    target_farm = get_or_create_user_farm(target_user)
    client.login(username='view-empty-target', password='password')

    response = client.post(reverse('farm_settings'), {
        'import_backup': '1',
        'confirm_empty_import': 'on',
        'backup_file': backup_file,
    })

    assert response.status_code == 302
    target_farm.refresh_from_db()
    assert target_farm.name == 'Importowane gospodarstwo'
    assert SowModel.objects.filter(farm=target_farm, ear_tag='SOW-BACKUP').exists()
    assert AuditLogModel.objects.filter(farm=target_farm, action='USER_BACKUP_IMPORT').exists()


@pytest.mark.django_db
def test_export_user_data_view_contains_only_current_farm_data(client):
    user = User.objects.create_user(username='export-owner', password='password')
    farm = get_or_create_user_farm(user)
    own_sow = SowModel.objects.create(farm=farm, ear_tag='OWN-EXPORT')
    other_user = User.objects.create_user(username='export-other')
    other_farm = get_or_create_user_farm(other_user)
    SowModel.objects.create(farm=other_farm, ear_tag='OTHER-EXPORT')
    client.login(username='export-owner', password='password')

    response = client.get(reverse('export_user_data'))

    assert response.status_code == 200
    assert response['Content-Type'] == 'application/zip'
    payload = _payload_from_archive(response.content)
    exported_sows = payload['data']['sows.SowModel']
    assert [record['fields']['ear_tag'] for record in exported_sows] == [own_sow.ear_tag]
    assert AuditLogModel.objects.filter(farm=farm, action='USER_BACKUP_EXPORT').exists()


@pytest.mark.django_db
def test_admin_backup_restore_endpoints_require_superuser(client):
    staff = User.objects.create_user(username='staff-only', password='password', is_staff=True)
    client.login(username='staff-only', password='password')

    assert client.get(reverse('admin_database_backup')).status_code == 403
    assert client.post(reverse('admin_database_restore')).status_code == 403


@pytest.mark.django_db
def test_admin_restore_view_requires_explicit_empty_restore_confirmation(client):
    admin = User.objects.create_superuser(username='restore-confirm-admin', password='password', email='admin@example.com')
    farm = get_or_create_user_farm(admin)
    SowModel.objects.create(farm=farm, ear_tag='RESTORE-CONFIRM')
    client.login(username='restore-confirm-admin', password='password')

    response = client.post(reverse('admin_database_restore'), {
        'backup_file': SimpleUploadedFile('database.zip', b'not-used'),
    })

    assert response.status_code == 302
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    assert any('Potwierdź' in message for message in messages)
    assert SowModel.objects.filter(farm=farm, ear_tag='RESTORE-CONFIRM').exists()


@pytest.mark.django_db
def test_admin_restore_view_reports_non_empty_database(client):
    admin = User.objects.create_superuser(username='backup-admin', password='password', email='admin@example.com')
    farm = get_or_create_user_farm(admin)
    SowModel.objects.create(farm=farm, ear_tag='ADMIN-EXISTING')
    archive, _ = build_database_backup()
    client.login(username='backup-admin', password='password')

    response = client.post(reverse('admin_database_restore'), {
        'confirm_empty_restore': 'on',
        'backup_file': SimpleUploadedFile('database.zip', archive),
    })

    assert response.status_code == 302
    messages = [str(message) for message in get_messages(response.wsgi_request)]
    assert any('baza ma już dane biznesowe' in message for message in messages)
    assert SowModel.objects.filter(ear_tag='ADMIN-EXISTING').exists()


@pytest.mark.django_db
def test_replace_farm_backup_restores_finished_feed_and_removes_previous_data():
    source_user = User.objects.create_user(username='replace-source')
    source_farm = get_or_create_user_farm(source_user)
    product = FeedProductModel.objects.create(farm=source_farm, name='Bebito', source_type=FeedProductModel.SourceTypes.PURCHASED_READY)
    delivery = ReadyFeedDeliveryModel.objects.create(farm=source_farm, product=product, date=date(2026, 7, 1), quantity_kg=Decimal('100.00'), price_per_kg=Decimal('2.00000'), total_cost=Decimal('200.00'))
    FinishedFeedBatchModel.objects.create(farm=source_farm, product=product, batch_date=delivery.date, initial_quantity_kg=delivery.quantity_kg, remaining_quantity_kg=delivery.quantity_kg, cost_per_kg=delivery.price_per_kg, total_cost=delivery.total_cost, ready_feed_delivery=delivery)
    backup = _user_backup_fixture(source_user, source_farm)

    target_user = User.objects.create_user(username='replace-target')
    target_farm = get_or_create_user_farm(target_user)
    SowModel.objects.create(farm=target_farm, ear_tag='DO-USUNIECIA')
    counts = import_user_backup(backup, target_farm, mode='REPLACE_FARM')

    assert not SowModel.objects.filter(farm=target_farm).exists()
    restored = FeedProductModel.objects.get(farm=target_farm, name='Bebito')
    assert restored.batches.get().remaining_quantity_kg == Decimal('100.00')
    assert counts['partie gotowej paszy'] == 1


@pytest.mark.django_db
def test_add_missing_import_does_not_duplicate_existing_ingredient():
    source_user = User.objects.create_user(username='merge-source')
    source_farm = get_or_create_user_farm(source_user)
    IngredientModel.objects.create(farm=source_farm, name='Pszenica')
    IngredientModel.objects.create(farm=source_farm, name='Jęczmień')
    backup = _user_backup_fixture(source_user, source_farm)
    target_user = User.objects.create_user(username='merge-target')
    target_farm = get_or_create_user_farm(target_user)
    IngredientModel.objects.create(farm=target_farm, name='Pszenica')

    import_user_backup(backup, target_farm, mode='ADD_MISSING')

    assert IngredientModel.objects.filter(farm=target_farm, name='Pszenica').count() == 1
    assert IngredientModel.objects.filter(farm=target_farm, name='Jęczmień').count() == 1


@pytest.mark.django_db
def test_settings_backup_flow_shows_preview_before_replace(client):
    source_user = User.objects.create_user(username='preview-source')
    source_farm = get_or_create_user_farm(source_user)
    IngredientModel.objects.create(farm=source_farm, name='Soja')
    backup = _user_backup_fixture(source_user, source_farm)
    target_user = User.objects.create_user(username='preview-target', password='password')
    target_farm = get_or_create_user_farm(target_user)
    IngredientModel.objects.create(farm=target_farm, name='Stary składnik')
    client.login(username='preview-target', password='password')

    preview = client.post(reverse('farm_settings'), {'analyze_backup': '1', 'backup_file': backup})
    assert preview.status_code == 200
    assert 'Podsumowanie kopii' in preview.content.decode()
    assert IngredientModel.objects.filter(farm=target_farm, name='Stary składnik').exists()
    token = preview.context['apply_form'].initial['preview_token']
    applied = client.post(reverse('farm_settings'), {
        'apply_backup': '1', 'preview_token': token, 'import_mode': 'REPLACE_FARM',
        'confirm_replace': 'on', 'confirmation': 'ZASTĄP DANE GOSPODARSTWA',
    })
    assert applied.status_code == 302
    assert not IngredientModel.objects.filter(farm=target_farm, name='Stary składnik').exists()
    assert IngredientModel.objects.filter(farm=target_farm, name='Soja').exists()


@pytest.mark.django_db(transaction=True)
def test_admin_database_replace_requires_preview_and_replaces_everything(client):
    admin_user = User.objects.create_superuser(username='full-replace-admin', password='password', email='admin@example.com')
    farm = get_or_create_user_farm(admin_user)
    SowModel.objects.create(farm=farm, ear_tag='W-KOPII')
    archive, _ = build_database_backup()
    SowModel.objects.create(farm=farm, ear_tag='PO-KOPII')
    client.login(username='full-replace-admin', password='password')

    preview = client.post(reverse('admin_database_restore'), {
        'analyze_database_backup': '1',
        'backup_file': SimpleUploadedFile('database.zip', archive),
    })
    assert preview.status_code == 200
    assert b'Podsumowanie' in preview.content
    token = preview.context['database_backup_token']
    response = client.post(reverse('admin_database_restore'), {
        'preview_token': token,
        'confirm_replace': 'on',
        'confirmation': 'ZASTĄP CAŁĄ BAZĘ DANYCH',
    })
    assert response.status_code == 302
    assert SowModel.objects.filter(ear_tag='W-KOPII').exists()
    assert not SowModel.objects.filter(ear_tag='PO-KOPII').exists()
