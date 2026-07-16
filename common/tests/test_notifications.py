from pathlib import Path

from django import forms
from django.contrib.messages import constants
from django.contrib.messages.storage.base import Message
from django.template.loader import render_to_string


def test_message_component_exposes_one_central_notification_queue():
    html = render_to_string(
        "components/messages.html",
        {
            "messages": [
                Message(constants.SUCCESS, "Składnik został dodany."),
                Message(constants.ERROR, "Nie udało się usunąć składnika."),
            ]
        },
    )

    assert html.count("data-notification-center") == 1
    assert 'data-notification-type="success"' in html
    assert 'data-notification-type="error"' in html
    assert 'data-success-timeout="3200"' in html
    assert 'data-error-timeout="8000"' in html
    assert "notification-icon-success" in html
    assert "notification-icon-error" in html
    assert 'data-notification-confirm' in html
    assert "message-stack" not in html
    assert "alert-success" not in html
    assert "alert-error" not in html


def test_form_error_summary_is_routed_to_notification_center():
    class ExampleForm(forms.Form):
        name = forms.CharField()

    form = ExampleForm(data={})
    assert not form.is_valid()

    html = render_to_string("components/form_errors.html", {"form": form})

    assert "data-notification-source" in html
    assert 'data-notification-form-errors="true"' in html
    assert 'data-notification-type="error"' in html
    assert "Popraw oznaczone pola" in html
    assert "alert-error" not in html


def test_old_message_stack_styles_are_removed():
    project_root = Path(__file__).resolve().parents[2]
    base_css = (project_root / "static/css/base/base.css").read_text(encoding="utf-8")
    responsive_css = (project_root / "static/css/pages/responsive.css").read_text(encoding="utf-8")
    messages_css = (project_root / "static/css/components/messages.css").read_text(encoding="utf-8")

    assert ".message-stack" not in base_css
    assert ".message-stack" not in responsive_css
    assert ".alert-success" not in messages_css
    assert ".alert-error" not in messages_css
    assert ".notification-center" in messages_css
