from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from farms.services.farm_service import get_or_create_user_farm
from sales.models import PigSaleModel
from sales.services.sale_form_service import SalePdfImportResult


@pytest.fixture
def sales_client(client):
    user = User.objects.create_user(username="pdf-user", password="password")
    get_or_create_user_farm(user)
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_pdf_import_requires_a_file(sales_client):
    response = sales_client.post(reverse("add_sale"), {"import_pdf": "1"})
    assert response.status_code == 200
    assert "Wybierz plik PDF" in response.content.decode()
    assert not PigSaleModel.objects.exists()


@pytest.mark.django_db
def test_pdf_import_rejects_corrupted_pdf_and_pdf_without_table(sales_client):
    corrupted = SimpleUploadedFile("settlement.pdf", b"not-pdf", content_type="application/pdf")
    response = sales_client.post(reverse("add_sale"), {"import_pdf": "1", "settlement_pdf": corrupted})
    assert response.status_code == 200
    assert "prawidłowym dokumentem PDF" in response.content.decode()

    no_table = SimpleUploadedFile("empty.pdf", b"%PDF-1.4\nno supported streams", content_type="application/pdf")
    response = sales_client.post(reverse("add_sale"), {"import_pdf": "1", "settlement_pdf": no_table})
    assert response.status_code == 200
    assert "Nie udało się odczytać tekstu" in response.content.decode()
    assert not PigSaleModel.objects.exists()


@pytest.mark.django_db
def test_pdf_parser_warnings_are_shown_and_preview_does_not_save(sales_client):
    uploaded = SimpleUploadedFile("settlement.pdf", b"%PDF-1.4\nfake", content_type="application/pdf")
    result = SalePdfImportResult(
        form_initial={"document_number": "DOC/1"},
        row_initial=[],
        warnings=["Format wymaga ręcznego sprawdzenia."],
        has_rows=False,
    )
    with patch("sales.views.SaleFormService.parse_pdf_import", return_value=result):
        response = sales_client.post(reverse("add_sale"), {"import_pdf": "1", "settlement_pdf": uploaded})
    assert response.status_code == 200
    assert "Format wymaga ręcznego sprawdzenia" in response.content.decode()
    assert not PigSaleModel.objects.exists()
