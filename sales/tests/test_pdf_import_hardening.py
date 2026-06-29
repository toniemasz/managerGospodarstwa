from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from farms.services.farm_service import get_or_create_user_farm
from sales.models import PigSaleModel
from sales.services.pdf_import_service import PdfTextItem, SaleSettlementPdfParser
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


def test_pdf_parser_warns_about_invalid_date_and_numbers(monkeypatch):
    parser = SaleSettlementPdfParser()
    items = [
        PdfTextItem(10, 760, "Data uboju: 2026-13-01"),
        PdfTextItem(10, 740, "Dokument nr: DOC/1"),
        PdfTextItem(40, 700, "Lp"),
        PdfTextItem(70, 700, "Klasa"),
        PdfTextItem(45, 650, "1"),
        PdfTextItem(75, 650, "E"),
        PdfTextItem(105, 650, "brak"),
        PdfTextItem(145, 650, "abc"),
        PdfTextItem(205, 650, "90,50"),
        PdfTextItem(255, 650, "57,20"),
        PdfTextItem(320, 650, "8,50"),
        PdfTextItem(370, 650, "850,00"),
        PdfTextItem(430, 650, "68,00"),
        PdfTextItem(480, 650, "918,00"),
        PdfTextItem(10, 500, "Razem:"),
    ]
    monkeypatch.setattr(parser, "_extract_text_pages", lambda data: [items])

    result = parser.parse(BytesIO(b"%PDF-1.4"))

    assert "sale_date" not in result.sale_fields
    assert result.rows[0]["quantity"] is None
    assert result.rows[0]["weight"] is None
    assert result.rows[0]["avg_weight"] == Decimal("90.50")
    warnings = " ".join(result.warnings)
    assert "daty uboju" in warnings
    assert "ilość" in warnings
    assert "waga" in warnings


def test_pdf_parser_warns_when_table_is_missing(monkeypatch):
    parser = SaleSettlementPdfParser()
    items = [
        PdfTextItem(10, 760, "Data uboju: 2026-06-01"),
        PdfTextItem(10, 740, "Dokument nr: DOC/2"),
    ]
    monkeypatch.setattr(parser, "_extract_text_pages", lambda data: [items])

    result = parser.parse(BytesIO(b"%PDF-1.4"))

    assert result.sale_fields["sale_date"] == date(2026, 6, 1)
    assert result.rows == []
    assert "Nie znaleziono wierszy głównej tabeli rozliczenia." in result.warnings


def test_pdf_parser_does_not_extract_numbers_from_malformed_text():
    parser = SaleSettlementPdfParser()

    assert parser._parse_decimal("abc123") is None
    assert parser._parse_int("12a") is None
