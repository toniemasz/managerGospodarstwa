import pytest
from django.contrib.auth import get_user_model

from farms.models import FormSubmissionModel
from farms.services.farm_service import get_or_create_user_farm
from farms.services.idempotency import execute_once, new_submission_token


@pytest.mark.django_db
def test_submission_token_is_consumed_once():
    user = get_user_model().objects.create_user(username="once-owner")
    farm = get_or_create_user_farm(user)
    token = new_submission_token()
    calls = []

    first = execute_once(
        farm=farm,
        user=user,
        scope="test.operation",
        token=token,
        operation=lambda: calls.append("saved") or 7,
    )
    second = execute_once(
        farm=farm,
        user=user,
        scope="test.operation",
        token=token,
        operation=lambda: calls.append("duplicate"),
    )

    assert first.executed is True
    assert first.value == 7
    assert second.executed is False
    assert calls == ["saved"]
    assert FormSubmissionModel.objects.count() == 1


@pytest.mark.django_db
def test_failed_operation_does_not_consume_submission_token():
    user = get_user_model().objects.create_user(username="retry-owner")
    farm = get_or_create_user_farm(user)
    token = new_submission_token()

    with pytest.raises(RuntimeError, match="temporary failure"):
        execute_once(
            farm=farm,
            user=user,
            scope="test.retry",
            token=token,
            operation=lambda: (_ for _ in ()).throw(RuntimeError("temporary failure")),
        )

    retried = execute_once(
        farm=farm,
        user=user,
        scope="test.retry",
        token=token,
        operation=lambda: "saved",
    )

    assert retried.executed is True
    assert retried.value == "saved"
    assert FormSubmissionModel.objects.filter(scope="test.retry").count() == 1
