from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_formset_controller_clones_table_rows_through_template_content():
    app_js = (PROJECT_ROOT / "static/js/core/app.js").read_text(encoding="utf-8")

    assert "parsedTemplate.content.firstElementChild" in app_js
    assert "wrapper.firstElementChild" not in app_js


def test_settings_tabs_implement_arrow_home_and_end_keyboard_navigation():
    settings_js = (PROJECT_ROOT / "static/js/pages/settings.js").read_text(encoding="utf-8")

    for key in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert f"event.key === '{key}'" in settings_js
