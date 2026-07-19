import json
import re

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import override_settings
from datetime import date, timedelta

from farms.models import AuditLogModel
from sows.models import MortalityReportModel, SowEventModel, SowModel, VaccinationPlanModel
from farms.services.farm_service import get_or_create_user_farm
from sows.services.sow_repository import SowRepository


def response_messages(response):
    return [str(message) for message in get_messages(response.wsgi_request)]


@pytest.mark.django_db
class TestSowViews:
    @pytest.fixture
    def setup_client(self, client):
        user = User.objects.create_user(username='testuser', password='password')
        client.user = user
        client.farm = get_or_create_user_farm(user)
        client.login(username='testuser', password='password')
        return client

    @override_settings(DEBUG=False, TESTING=False, ALLOWED_HOSTS=['testserver'])
    def test_login_view_redirects_to_https_in_production(self, client):
        response = client.get(reverse('login'))

        assert response.status_code == 302
        assert response['Location'].startswith('https://testserver/login/')

    def test_dashboard_view_access(self, setup_client):
        url = reverse('dashboard')
        response = setup_client.get(url)
        assert response.status_code == 200

    def test_modules_home_view_access(self, setup_client):
        response = setup_client.get(reverse('modules_home'))
        assert response.status_code == 200

    def test_add_sow_view_get(self, setup_client):
        url = reverse('add_sow')
        response = setup_client.get(url)
        assert response.status_code == 200

    def test_add_sow_view_post(self, setup_client):
        url = reverse('add_sow')
        response = setup_client.post(url, {
            'ear_tag': 'NEW-SOW-99',
            'entry_date': '2023-10-10'
        })
        assert response.status_code == 302 # Przekierowanie po sukcesie
        assert SowModel.objects.filter(ear_tag='NEW-SOW-99', farm=setup_client.farm).exists()
        assert "Maciora została dodana." in response_messages(response)

    def test_sow_detail_view(self, setup_client):
        sow = SowModel.objects.create(ear_tag="DETAIL-1", farm=setup_client.farm)
        url = reverse('sow_detail', args=[sow.id])
        response = setup_client.get(url)
        assert response.status_code == 200

    def test_sow_detail_edit_rejects_another_active_sow_number(self, setup_client):
        existing = SowModel.objects.create(ear_tag='DETAIL-EXISTING', farm=setup_client.farm)
        edited = SowModel.objects.create(ear_tag='DETAIL-EDITED', farm=setup_client.farm)

        response = setup_client.post(reverse('sow_detail', args=[edited.id]), {
            'edit_sow': '1',
            'ear_tag': f' {existing.ear_tag.lower()} ',
            'entry_date': edited.entry_date.isoformat(),
        })

        edited.refresh_from_db()
        assert response.status_code == 200
        assert edited.ear_tag == 'DETAIL-EDITED'
        assert 'Aktywna maciora o tym numerze' in response.context['form'].errors['ear_tag'][0]

    def test_add_vaccination_plan_view_get_and_post(self, setup_client):
        get_response = setup_client.get(reverse('add_vaccination_plan'))
        content = get_response.content.decode()

        assert get_response.status_code == 200
        assert 'id="vaccination-plan-form"' in content
        assert 'id="id_trigger_type"' in content
        assert 'id="vaccination-before-farrowing-section"' in content
        assert 'id="vaccination-after-event-section"' in content
        assert 'id="vaccination-interval-section"' in content
        assert 'id="vaccination-selected-sows-section"' in content

        post_response = setup_client.post(
            reverse('add_vaccination_plan'),
            {
                'name': 'Parwowiroza',
                'trigger_type': 'BEFORE_FARROWING',
                'days_before_farrowing': '21',
                'reminder_days_ahead': '7',
                'scope': 'ALL',
            },
        )

        assert post_response.status_code == 302

        plan = VaccinationPlanModel.objects.get(
            name='Parwowiroza',
            farm=setup_client.farm,
        )

        assert plan.days_before_farrowing == 21
        assert plan.days_after_event is None
        assert plan.event_source is None
        assert plan.interval_value is None
        assert plan.interval_unit is None
        assert plan.schedule_mode is None
        assert plan.first_due_date is None
        assert plan.scope == VaccinationPlanModel.SCOPE_ALL

    def test_edit_plan_can_reinclude_excluded_sow(self, setup_client):
        sow = SowModel.objects.create(
            farm=setup_client.farm,
            ear_tag='REINCLUDE',
        )
        plan = VaccinationPlanModel.objects.create(
            farm=setup_client.farm,
            name='Różyca',
            interval_value=1,
            interval_unit='YEARS',
            interval_months=None,
            schedule_mode='FIXED',
            first_due_date=date(2026, 7, 1),
            scope='ALL',
            reminder_days_ahead=7,
        )
        plan.excluded_sows.add(sow)

        response = setup_client.post(
            reverse('edit_vaccination_plan', args=[plan.id]),
            {
                'name': plan.name,
                'trigger_type': 'INTERVAL',
                'interval_value': '1',
                'interval_unit': 'YEARS',
                'schedule_mode': 'FIXED',
                'first_due_date': '2026-07-01',
                'scope': 'ALL',
                'reminder_days_ahead': '7',
                'reinclude_sows': [str(sow.id)],
            },
        )

        assert response.status_code == 302

        plan.refresh_from_db()

        assert not plan.excluded_sows.filter(id=sow.id).exists()
        assert plan.interval_value == 1
        assert plan.interval_unit == VaccinationPlanModel.INTERVAL_YEARS
        assert plan.schedule_mode == VaccinationPlanModel.SCHEDULE_FIXED
        assert plan.first_due_date == date(2026, 7, 1)

    def test_delete_plan_is_soft_and_farm_scoped(self, setup_client):
        plan = VaccinationPlanModel.objects.create(
            farm=setup_client.farm,
            name='Soft delete',
            days_before_farrowing=21,
        )
        other_user = User.objects.create_user(username='plan-delete-other')
        other_farm = get_or_create_user_farm(other_user)
        foreign_plan = VaccinationPlanModel.objects.create(
            farm=other_farm,
            name='Foreign plan',
            days_before_farrowing=21,
        )

        foreign_response = setup_client.post(reverse('delete_vaccination_plan', args=[foreign_plan.id]))
        response = setup_client.post(reverse('delete_vaccination_plan', args=[plan.id]))

        assert foreign_response.status_code == 404
        assert response.status_code == 302
        plan.refresh_from_db()
        assert plan.is_active is False

    def test_edit_vaccination_plan_changes_trigger_and_clears_old_schedule(
            self,
            setup_client,
    ):
        plan = VaccinationPlanModel.objects.create(
            farm=setup_client.farm,
            name='Różyca cykliczna',
            interval_months=4,
            interval_value=4,
            interval_unit=VaccinationPlanModel.INTERVAL_MONTHS,
            schedule_mode=VaccinationPlanModel.SCHEDULE_FIXED,
            first_due_date=date(2026, 7, 12),
            reminder_days_ahead=7,
            scope=VaccinationPlanModel.SCOPE_ALL,
        )

        response = setup_client.post(
            reverse('edit_vaccination_plan', args=[plan.id]),
            {
                'name': plan.name,
                'trigger_type': 'BEFORE_FARROWING',
                'days_before_farrowing': '21',
                'reminder_days_ahead': '7',
                'scope': 'ALL',
            },
        )

        assert response.status_code == 302

        plan.refresh_from_db()

        assert plan.days_before_farrowing == 21
        assert plan.days_after_event is None
        assert plan.event_source is None
        assert plan.interval_value is None
        assert plan.interval_unit is None
        assert plan.interval_months is None
        assert plan.schedule_mode is None
        assert plan.first_due_date is None

    def test_add_edit_and_delete_event_views(self, setup_client):
        sow = SowModel.objects.create(ear_tag="FLOW-1", farm=setup_client.farm)

        add_get = setup_client.get(reverse('add_event', args=[sow.id]))
        assert add_get.status_code == 200

        add_post = setup_client.post(reverse('add_event', args=[sow.id]), {
            'event_type': 'INSEMINATION',
            'event_date': '2026-06-01',
            'technician': 'Jan',
        })
        assert add_post.status_code == 302
        assert "Zdarzenie zostało dodane." in response_messages(add_post)
        event = SowEventModel.objects.get(sow=sow)
        assert event.details == {'technician': 'Jan'}

        edit_get = setup_client.get(reverse('edit_event', args=[event.id]))
        assert edit_get.status_code == 200

        edit_post = setup_client.post(reverse('edit_event', args=[event.id]), {
            'event_type': 'PREGNANCY_CHECK',
            'event_date': '2026-06-30',
            'pregnancy_result': 'TAK',
        })
        assert edit_post.status_code == 302
        assert "Zdarzenie zostało zaktualizowane." in response_messages(edit_post)
        event.refresh_from_db()
        assert event.event_type == 'PREGNANCY_CHECK'
        assert event.details == {'result': 'TAK'}

        delete_post = setup_client.post(reverse('delete_event', args=[event.id]))
        assert delete_post.status_code == 302
        assert "Zdarzenie zostało usunięte." in response_messages(delete_post)
        assert not SowEventModel.objects.filter(id=event.id).exists()

    def test_bulk_pregnancy_check_view_creates_events(self, setup_client):
        sow = SowModel.objects.create(ear_tag="USG-1", farm=setup_client.farm)
        SowEventModel.objects.create(
            sow=sow,
            event_type='INSEMINATION',
            event_date=date.today() - timedelta(days=31),
            details={},
        )

        get_response = setup_client.get(reverse('bulk_pregnancy_check'))
        assert get_response.status_code == 200

        post_response = setup_client.post(reverse('bulk_pregnancy_check'), {
            f'result_{sow.id}': 'NIE',
        })

        assert post_response.status_code == 302
        assert "Zapisano wyniki badań macior: 1." in response_messages(post_response)
        assert SowEventModel.objects.filter(
            sow=sow,
            event_type='PREGNANCY_CHECK',
            details={'result': 'NIE'},
        ).exists()

    def test_bulk_vaccinate_confirmation_and_save(self, setup_client):
        sow = SowModel.objects.create(
            ear_tag="VAC-1",
            farm=setup_client.farm,
            entry_date=date.today() - timedelta(days=30),
        )
        plan = VaccinationPlanModel.objects.create(
            name='Parwo',
            interval_months=1,
            interval_value=1,
            interval_unit='MONTHS',
            schedule_mode='FROM_LAST_COMPLETED',
            first_due_date=date.today(),
            reminder_days_ahead=7,
            farm=setup_client.farm,
        )

        dashboard = setup_client.get(reverse('dashboard'))
        dashboard_content = dashboard.content.decode()
        assert dashboard.status_code == 200
        assert "Do obsługi" in dashboard_content
        assert "Szczepienie maciory VAC-1" in dashboard_content

        confirm_page = setup_client.get(reverse('bulk_vaccinate'))
        assert confirm_page.status_code == 200
        content = confirm_page.content.decode()
        assert "Panel szczepień" in content
        assert "Maciora VAC-1" in content

        save_response = setup_client.post(reverse('bulk_vaccinate'), {
            'confirm': 'yes',
            'sow_ids': [str(sow.id)],
            'vaccine_name': 'Parwo',
            'cycle_id': f"periodic_{plan.id}_{date.today().isoformat()}",
            'plan_id': str(plan.id),
            'scheduled_date': date.today().isoformat(),
        })

        assert save_response.status_code == 302
        event = SowEventModel.objects.get(sow=sow, event_type='VACCINATION')
        assert event.details['vaccine_name'] == 'Parwo'
        assert event.details['cycle_id'] == f"periodic_{plan.id}_{date.today().isoformat()}"
        assert event.details['scheduled_date'] == date.today().isoformat()
        assert event.vaccination_plan == plan

    def test_archive_and_archived_sows_views(self, setup_client):
        sow = SowModel.objects.create(ear_tag="ARCHIVE-ME", farm=setup_client.farm)

        archive_response = setup_client.post(reverse('delete_sow', args=[sow.id]), {'archive': 'on'})
        assert archive_response.status_code == 302
        assert "Maciora została zarchiwizowana." in response_messages(archive_response)
        sow.refresh_from_db()
        assert sow.is_archived is True
        assert sow.archived_at is not None

        archived_response = setup_client.get(reverse('archived_sows'))
        assert archived_response.status_code == 200

    def test_general_statistics_view_handles_invalid_months(self, setup_client):
        response = setup_client.get(reverse('general_statistics'), {
            'metric': 'born_alive',
            'months': 'not-a-number',
            'order': 'asc',
        })

        assert response.status_code == 200

    def test_general_statistics_chart_data_is_valid_json(self, setup_client):
        sow = SowModel.objects.create(ear_tag='CHART-1', farm=setup_client.farm)
        SowEventModel.objects.create(
            sow=sow,
            event_type='FARROWING',
            event_date=date.today(),
            details={'born_alive': 12},
        )

        response = setup_client.get(reverse('general_statistics'), {'period': 'all'})
        html = response.content.decode()
        labels_match = re.search(
            r'<script id="trend-chart-labels" type="application/json">(.*?)</script>',
            html,
        )
        values_match = re.search(
            r'<script id="trend-chart-values" type="application/json">(.*?)</script>',
            html,
        )

        assert response.status_code == 200
        assert labels_match is not None
        assert values_match is not None
        assert json.loads(labels_match.group(1)) == [date.today().strftime('%Y-%m')]
        assert json.loads(values_match.group(1)) == [12]

    def test_unauthenticated_user_redirected(self, client):
        # Bez logowania powinno wyrzucić 302 (do strony logowania)
        url = reverse('dashboard')
        response = client.get(url)
        assert response.status_code == 302

    def test_dashboard_shows_only_current_farm_sows(self, setup_client):
        other_user = User.objects.create_user(username='other-sows', password='password')
        other_farm = get_or_create_user_farm(other_user)

        SowModel.objects.create(ear_tag="OWN-1", farm=setup_client.farm)
        SowModel.objects.create(ear_tag="OTHER-1", farm=other_farm)

        response = setup_client.get(reverse('dashboard'))

        assert response.status_code == 200
        assert "OWN-1" in response.content.decode()
        assert "OTHER-1" not in response.content.decode()

    def test_dashboard_renders_more_than_first_page_of_sows(self, setup_client):
        for index in range(15):
            SowModel.objects.create(ear_tag=f"PAGE-{index:02d}", farm=setup_client.farm)

        response = setup_client.get(reverse('dashboard'))
        content = response.content.decode()

        assert response.status_code == 200
        assert "PAGE-00" in content
        assert "PAGE-14" in content

    def test_single_bulk_event_mode_has_only_one_row_without_add_button(self, setup_client):
        response = setup_client.get(f"{reverse('bulk_sow_events')}?rows=1")
        content = response.content.decode()

        assert response.status_code == 200
        assert 'id="add-bulk-event-row"' not in content
        assert 'name="events-TOTAL_FORMS" value="1"' in content

    def test_bulk_sow_events_view_creates_valid_events(self, setup_client):
        sow = SowModel.objects.create(ear_tag="BULK-1", farm=setup_client.farm)

        response = setup_client.post(reverse('bulk_sow_events'), {
            'events-TOTAL_FORMS': '1',
            'events-INITIAL_FORMS': '0',
            'events-MIN_NUM_FORMS': '0',
            'events-MAX_NUM_FORMS': '1000',
            'events-0-sow_ear_tag': sow.ear_tag,
            'events-0-event_type': 'INSEMINATION',
            'events-0-event_date': sow.entry_date.isoformat(),
            'events-0-technician': 'Jan',
        })

        assert response.status_code == 302
        assert SowEventModel.objects.filter(
            sow=sow,
            event_type='INSEMINATION',
            details={'technician': 'Jan'},
        ).exists()

    def test_bulk_sow_events_view_blocks_invalid_cycle_event(self, setup_client):
        sow = SowModel.objects.create(ear_tag="BULK-BLOCK", farm=setup_client.farm)

        response = setup_client.post(reverse('bulk_sow_events'), {
            'events-TOTAL_FORMS': '1',
            'events-INITIAL_FORMS': '0',
            'events-MIN_NUM_FORMS': '0',
            'events-MAX_NUM_FORMS': '1000',
            'events-0-sow_ear_tag': sow.ear_tag,
            'events-0-event_type': 'FARROWING',
            'events-0-event_date': '2026-06-20',
            'events-0-born_alive': '10',
            'events-0-born_dead': '1',
        })

        assert response.status_code == 200
        assert not SowEventModel.objects.filter(sow=sow, event_type='FARROWING').exists()

    def test_bulk_sow_events_view_blocks_out_of_order_rows_for_same_sow(self, setup_client):
        sow = SowModel.objects.create(ear_tag="BULK-ORDER", farm=setup_client.farm)

        response = setup_client.post(reverse('bulk_sow_events'), {
            'events-TOTAL_FORMS': '2',
            'events-INITIAL_FORMS': '0',
            'events-MIN_NUM_FORMS': '0',
            'events-MAX_NUM_FORMS': '1000',
            'events-0-sow_ear_tag': sow.ear_tag,
            'events-0-event_type': 'INSEMINATION',
            'events-0-event_date': '2026-06-20',
            'events-0-technician': 'Jan',
            'events-1-sow_ear_tag': sow.ear_tag,
            'events-1-event_type': 'INSEMINATION',
            'events-1-event_date': '2026-06-19',
            'events-1-technician': 'Jan',
        })

        assert response.status_code == 200
        assert "chronologicznie od góry do dołu" in response.content.decode()
        assert not SowEventModel.objects.filter(sow=sow).exists()

    def test_add_miscarriage_event_only_for_pregnant_sow(self, setup_client):
        pregnant_sow = SowModel.objects.create(ear_tag="MISC-PREG", farm=setup_client.farm)
        SowEventModel.objects.create(
            sow=pregnant_sow,
            event_type='INSEMINATION',
            event_date=date.today() - timedelta(days=40),
            details={'technician': 'Jan'},
        )
        SowEventModel.objects.create(
            sow=pregnant_sow,
            event_type='PREGNANCY_CHECK',
            event_date=date.today() - timedelta(days=10),
            details={'result': 'TAK'},
        )

        response = setup_client.post(reverse('add_event', args=[pregnant_sow.id]), {
            'event_type': 'MISCARRIAGE',
            'event_date': date.today().isoformat(),
        })

        assert response.status_code == 302
        miscarriage = SowEventModel.objects.get(sow=pregnant_sow, event_type='MISCARRIAGE')
        assert miscarriage.details == {}
        assert miscarriage.created_at is not None
        assert SowRepository(farm=setup_client.farm).get_sow_by_id(pregnant_sow.id).status == 'IDLE'

        idle_sow = SowModel.objects.create(ear_tag="MISC-IDLE", farm=setup_client.farm)
        blocked_response = setup_client.post(reverse('add_event', args=[idle_sow.id]), {
            'event_type': 'MISCARRIAGE',
            'event_date': date.today().isoformat(),
        })

        assert blocked_response.status_code == 200
        assert not SowEventModel.objects.filter(sow=idle_sow, event_type='MISCARRIAGE').exists()

    def test_report_sow_mortality_archives_sow_and_keeps_history(self, setup_client):
        sow = SowModel.objects.create(ear_tag="DEAD-SOW", farm=setup_client.farm)
        event = SowEventModel.objects.create(
            sow=sow,
            event_type='INSEMINATION',
            event_date=date.today() - timedelta(days=20),
            details={'technician': 'Jan'},
        )

        response = setup_client.post(reverse('report_mortality'), {
            'mortality_type': 'sow',
            'sow': str(sow.id),
            'mortality_date': date.today().isoformat(),
            'quantity': '99',
            'reason': 'Nagły upadek',
            'note': 'Notatka testowa',
        })

        assert response.status_code == 302
        report = MortalityReportModel.objects.get(farm=setup_client.farm)
        assert report.sow == sow
        assert report.quantity == 1
        sow.refresh_from_db()
        assert sow.is_archived is True
        assert sow.archive_reason == SowModel.ARCHIVE_REASON_DEATH
        assert sow.death_date == date.today()
        assert sow.death_note == 'Notatka testowa'
        assert SowEventModel.objects.filter(id=event.id, sow=sow).exists()
        assert AuditLogModel.objects.filter(
            farm=setup_client.farm,
            action='CREATE',
            model_label='sows.MortalityReportModel',
        ).exists()
        assert AuditLogModel.objects.filter(
            farm=setup_client.farm,
            action='ARCHIVE',
            object_id=str(sow.id),
            metadata__archive_reason=SowModel.ARCHIVE_REASON_DEATH,
        ).exists()

    def test_report_mortality_form_uses_sow_number_suggestions_and_visible_quantity(self, setup_client):
        sow = SowModel.objects.create(ear_tag="1234", farm=setup_client.farm)
        SowModel.objects.create(ear_tag="1290", farm=setup_client.farm)
        other_user = User.objects.create_user(username='mortality-suggest-other', password='password')
        other_farm = get_or_create_user_farm(other_user)
        SowModel.objects.create(ear_tag="1255", farm=other_farm)

        response = setup_client.get(reverse('report_mortality'), {'mortality_type': 'sow'})
        content = response.content.decode()

        assert response.status_code == 200
        assert 'list="mortality-sow-options"' in content
        assert 'value="1234"' in content
        assert 'value="1290"' in content
        assert 'value="1255"' not in content
        assert 'id="sec_mortality_quantity" class="form-section dynamic-form-section"' in content
        assert 'id="id_quantity"' in content

        save_response = setup_client.post(reverse('report_mortality'), {
            'mortality_type': 'sow',
            'sow': '1234',
            'mortality_date': date.today().isoformat(),
            'reason': 'Nagły upadek',
        })

        assert save_response.status_code == 302
        report = MortalityReportModel.objects.get(farm=setup_client.farm)
        assert report.sow == sow
        assert report.quantity == 1

    def test_report_sow_mortality_blocks_archived_and_foreign_sows(self, setup_client):
        archived_sow = SowModel.objects.create(
            ear_tag="DEAD-ARCHIVED",
            farm=setup_client.farm,
            is_archived=True,
        )
        other_user = User.objects.create_user(username='mortality-other', password='password')
        other_farm = get_or_create_user_farm(other_user)
        foreign_sow = SowModel.objects.create(ear_tag="DEAD-FOREIGN", farm=other_farm)

        archived_response = setup_client.post(reverse('report_mortality'), {
            'mortality_type': 'sow',
            'sow': str(archived_sow.id),
            'mortality_date': date.today().isoformat(),
        })
        foreign_response = setup_client.post(reverse('report_mortality'), {
            'mortality_type': 'sow',
            'sow': str(foreign_sow.id),
            'mortality_date': date.today().isoformat(),
        })

        assert archived_response.status_code == 200
        assert foreign_response.status_code == 200
        assert not MortalityReportModel.objects.filter(farm=setup_client.farm).exists()
        foreign_sow.refresh_from_db()
        assert foreign_sow.is_archived is False

    def test_report_post_weaning_mortality_validates_quantity_and_future_date(self, setup_client):
        valid_response = setup_client.post(reverse('report_mortality'), {
            'mortality_type': MortalityReportModel.TYPE_PIGLET,
            'mortality_date': date.today().isoformat(),
            'quantity': '3',
            'reason': 'Choroba',
        })

        assert valid_response.status_code == 302
        report = MortalityReportModel.objects.get(farm=setup_client.farm)
        assert report.mortality_type == MortalityReportModel.TYPE_PIGLET
        assert report.sow is None
        assert report.quantity == 3

        invalid_response = setup_client.post(reverse('report_mortality'), {
            'mortality_type': MortalityReportModel.TYPE_PIGLET,
            'mortality_date': (date.today() + timedelta(days=1)).isoformat(),
            'quantity': '0',
        })

        assert invalid_response.status_code == 200
        assert MortalityReportModel.objects.filter(farm=setup_client.farm).count() == 1

    def test_mortality_list_is_farm_scoped_and_shows_post_weaning_stock(self, setup_client):
        own_sow = SowModel.objects.create(ear_tag="OWN-WEAN", farm=setup_client.farm)
        SowEventModel.objects.create(
            sow=own_sow,
            event_type='WEANING',
            event_date=date.today(),
            details={'count': 10},
        )
        MortalityReportModel.objects.create(
            farm=setup_client.farm,
            mortality_type=MortalityReportModel.TYPE_POST_WEANING,
            mortality_date=date.today(),
            quantity=2,
            reason='Widoczne',
        )

        other_user = User.objects.create_user(username='mortality-list-other', password='password')
        other_farm = get_or_create_user_farm(other_user)
        other_sow = SowModel.objects.create(ear_tag="OTHER-WEAN", farm=other_farm)
        SowEventModel.objects.create(
            sow=other_sow,
            event_type='WEANING',
            event_date=date.today(),
            details={'count': 20},
        )
        MortalityReportModel.objects.create(
            farm=other_farm,
            mortality_type=MortalityReportModel.TYPE_POST_WEANING,
            mortality_date=date.today(),
            quantity=5,
            reason='Ukryte',
        )

        response = setup_client.get(reverse('mortality_list'))
        content = response.content.decode()

        assert response.status_code == 200
        assert "Widoczne" in content
        assert "Ukryte" not in content
        assert response.context['post_weaning_stock'] == {
            'weaned_total': 10,
            'mortality_total': 2,
            'current_stock': 8,
        }
