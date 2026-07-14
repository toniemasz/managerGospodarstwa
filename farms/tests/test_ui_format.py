import re
from decimal import Decimal
from pathlib import Path

from farms.templatetags.ui_format import smart_number_value, smart_unit


def test_smart_number_trims_empty_fraction():
    assert smart_number_value(Decimal("2.00")) == "2"
    assert smart_number_value("2,00") == "2"
    assert smart_number_value("2.00") == "2"


def test_smart_number_keeps_meaningful_fraction():
    assert smart_number_value(Decimal("2.50")) == "2,5"


def test_smart_unit_formats_number_with_unit():
    assert smart_unit(Decimal("120.00"), "kg") == "120 kg"


def test_legacy_app_css_imports_existing_split_stylesheets():
    css_root = Path(__file__).resolve().parents[2] / "static" / "css"
    app_css = (css_root / "app.css").read_text(encoding="utf-8")
    imports = re.findall(r'@import url\("([^"]+)"\)', app_css)

    assert imports
    assert all((css_root / imported_path).is_file() for imported_path in imports)
