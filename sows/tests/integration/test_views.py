import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from sows.models import SowModel

@pytest.mark.django_db
class TestSowViews:
    @pytest.fixture
    def setup_client(self, client):
        user = User.objects.create_user(username='testuser', password='password')
        client.login(username='testuser', password='password')
        return client

    def test_dashboard_view_access(self, setup_client):
        url = reverse('dashboard')
        response = setup_client.get(url)
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
        assert SowModel.objects.filter(ear_tag='NEW-SOW-99').exists()

    def test_sow_detail_view(self, setup_client):
        sow = SowModel.objects.create(ear_tag="DETAIL-1")
        url = reverse('sow_detail', args=[sow.id])
        response = setup_client.get(url)
        assert response.status_code == 200

    def test_unauthenticated_user_redirected(self, client):
        # Bez logowania powinno wyrzucić 302 (do strony logowania)
        url = reverse('dashboard')
        response = client.get(url)
        assert response.status_code == 302