import json
import re

import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import override_settings
from datetime import date, timedelta

from sows.models import SowEventModel, SowModel, VaccinationPlanModel
from farms.services.farm_service import get_or_create_user_farm

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

    def test_sow_detail_view(self, setup_client):
        sow = SowModel.objects.create(ear_tag="DETAIL-1", farm=setup_client.farm)
        url = reverse('sow_detail', args=[sow.id])
        response = setup_client.get(url)
        assert response.status_code == 200

    def test_add_vaccination_plan_view_get_and_post(self, setup_client):
        get_response = setup_client.get(reverse('add_vaccination_plan'))
        assert get_response.status_code == 200

        post_response = setup_client.post(reverse('add_vaccination_plan'), {
            'name': 'Parwowiroza',
            'days_before_farrowing': '21',
            'reminder_days_ahead': '7',
        })

        assert post_response.status_code == 302
        assert VaccinationPlanModel.objects.filter(name='Parwowiroza', farm=setup_client.farm).exists()

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
        event.refresh_from_db()
        assert event.event_type == 'PREGNANCY_CHECK'
        assert event.details == {'result': 'TAK'}

        delete_post = setup_client.post(reverse('delete_event', args=[event.id]))
        assert delete_post.status_code == 302
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
        VaccinationPlanModel.objects.create(
            name='Parwo',
            interval_months=1,
            reminder_days_ahead=7,
            farm=setup_client.farm,
        )

        dashboard = setup_client.get(reverse('dashboard'))
        dashboard_content = dashboard.content.decode()
        assert dashboard.status_code == 200
        assert "Oczekujące szczepienia" in dashboard_content
        assert "Liczba szczepień do potwierdzenia" in dashboard_content

        confirm_page = setup_client.get(reverse('bulk_vaccinate'))
        assert confirm_page.status_code == 200
        content = confirm_page.content.decode()
        assert "Panel szczepień" in content
        assert "Maciora VAC-1" in content

        save_response = setup_client.post(reverse('bulk_vaccinate'), {
            'confirm': 'yes',
            'sow_ids': [str(sow.id)],
            'vaccine_name': 'Parwo',
            'cycle_id': f"cyclic_{date.today().strftime('%Y-%m-%d')}",
        })

        assert save_response.status_code == 302
        event = SowEventModel.objects.get(sow=sow, event_type='VACCINATION')
        assert event.details == {'vaccine_name': 'Parwo', 'cycle_id': f"cyclic_{date.today().strftime('%Y-%m-%d')}"}

    def test_archive_and_archived_sows_views(self, setup_client):
        sow = SowModel.objects.create(ear_tag="ARCHIVE-ME", farm=setup_client.farm)

        archive_response = setup_client.post(reverse('delete_sow', args=[sow.id]), {'archive': 'on'})
        assert archive_response.status_code == 302
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
            'events-0-event_date': '2026-06-20',
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
