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
from sales.number_parsing import parse_polish_decimal, parse_polish_int
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
    assert "daty sprzedaży/uboju" in warnings
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


def test_polish_number_parser_accepts_units_and_separators():
    assert parse_polish_decimal("231,30 kg") == Decimal("231.30")
    assert parse_polish_decimal("115,65 kg") == Decimal("115.65")
    assert parse_polish_decimal("6,05 zł/kg") == Decimal("6.05")
    assert parse_polish_int("1 szt.") == 1
    assert parse_polish_decimal("13 707,10 kg") == Decimal("13707.10")
    assert parse_polish_decimal("13\xa0707,10 kg") == Decimal("13707.10")
    assert parse_polish_decimal("5,25 zł/kg") == Decimal("5.25")


def test_pdf_parser_imports_sample_sale_settlement_rows_without_unit_warnings(monkeypatch):
    parser = SaleSettlementPdfParser()
    items = [
        PdfTextItem(59.5, 718.79, "Tatuaż:"),
        PdfTextItem(144.6, 718.79, "30178"),
        PdfTextItem(371.3, 718.79, "Data uboju: 2025-10-22"),
        PdfTextItem(371.3, 696.12, "Dokument nr: 197368"),
        PdfTextItem(48.4, 576.92, "Lp"),
        PdfTextItem(70.0, 576.92, "Klasa"),
        PdfTextItem(105.9, 576.92, "Ilość"),
        PdfTextItem(148.9, 576.92, "Waga"),
        PdfTextItem(198.5, 576.92, "Śr. waga"),
        PdfTextItem(249.1, 576.92, "Śr. mięsność"),
        PdfTextItem(321.9, 576.92, "Cena"),
        PdfTextItem(371.3, 576.92, "Wartość"),
        PdfTextItem(434.7, 576.92, "VAT"),
        PdfTextItem(466.2, 576.92, "Wartość brutto"),
        PdfTextItem(51.3, 443.69, "9"),
        PdfTextItem(76.7, 443.69, "U4"),
        PdfTextItem(111.3, 443.69, "2 szt."),
        PdfTextItem(146.8, 443.69, "231,30 kg"),
        PdfTextItem(198.1, 443.69, "115,65 kg"),
        PdfTextItem(263.8, 443.69, "53,8 %"),
        PdfTextItem(315.1, 443.69, "6,05 zł/kg"),
        PdfTextItem(374.9, 443.69, "1 399,37 zł"),
        PdfTextItem(425.0, 443.69, "111,95 zł"),
        PdfTextItem(488.3, 443.69, "1 511,32 zł"),
        PdfTextItem(48.8, 415.34, "11"),
        PdfTextItem(79.4, 415.34, "C"),
        PdfTextItem(111.3, 415.34, "4 szt."),
        PdfTextItem(146.8, 415.34, "486,40 kg"),
        PdfTextItem(198.1, 415.34, "121,60 kg"),
        PdfTextItem(263.8, 415.34, "55,7 %"),
        PdfTextItem(315.1, 415.34, "5,25 zł/kg"),
        PdfTextItem(374.9, 415.34, "2 553,60 zł"),
        PdfTextItem(425.0, 415.34, "204,29 zł"),
        PdfTextItem(488.3, 415.34, "2 757,89 zł"),
        PdfTextItem(45.4, 393.70, "Razem:"),
        PdfTextItem(158.7, 393.70, "13 707,10 kg"),
        PdfTextItem(272.1, 393.70, "135 szt."),
        PdfTextItem(385.5, 393.70, "Netto:"),
        PdfTextItem(442.2, 393.70, "92 817,53 zł"),
        PdfTextItem(45.4, 371.03, "Waga żywa:"),
        PdfTextItem(158.7, 371.03, "17 078,00 kg"),
        PdfTextItem(360.0, 371.03, "VAT (8%):"),
        PdfTextItem(450.7, 371.03, "7 425,40 zł"),
        PdfTextItem(45.4, 348.35, "Wybój:"),
        PdfTextItem(158.7, 348.35, "80,26 %"),
        PdfTextItem(382.7, 348.35, "Brutto:"),
        PdfTextItem(442.2, 348.35, "100 242,93 zł"),
        PdfTextItem(45.4, 325.67, "Średnia mięsność dla SEUROP:"),
        PdfTextItem(272.1, 325.67, "58,61 %"),
    ]
    monkeypatch.setattr(parser, "_extract_text_pages", lambda data: [items])

    result = parser.parse(BytesIO(b"%PDF-1.4"))

    assert result.sale_fields["sale_date"] == date(2025, 10, 22)
    assert result.sale_fields["document_number"] == "197368"
    assert result.sale_fields["tattoo"] == "30178"
    assert result.sale_fields["live_weight"] == Decimal("17078.00")
    assert result.sale_fields["dressing_percentage"] == Decimal("80.26")
    assert result.sale_fields["avg_meatiness_seurop"] == Decimal("58.61")
    assert result.rows[0] == {
        "line_no": 9,
        "meat_class": "U4",
        "quantity": 2,
        "weight": Decimal("231.30"),
        "avg_weight": Decimal("115.65"),
        "avg_meatiness": Decimal("53.8"),
        "price_per_kg": Decimal("6.05"),
        "net_value": Decimal("1399.37"),
        "vat_value": Decimal("111.95"),
        "gross_value": Decimal("1511.32"),
    }
    assert result.rows[1]["price_per_kg"] == Decimal("5.25")
    assert result.summary["total_weight"] == Decimal("13707.10")
    assert result.summary["quantity"] == 135
    assert result.warnings == []
