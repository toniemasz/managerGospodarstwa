from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar
from uuid import UUID, uuid4

from django.db import IntegrityError, transaction

from farms.models import FormSubmissionModel


ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class SubmissionResult(Generic[ResultT]):
    executed: bool
    value: ResultT | None = None


def new_submission_token() -> str:
    return str(uuid4())


def execute_once(*, farm, user, scope: str, token, operation: Callable[[], ResultT]) -> SubmissionResult[ResultT]:
    """Execute an operation once for a rendered form token, in the same transaction.

    A missing token keeps older integrations and tests compatible. Browser forms
    always receive a token; a present malformed token is treated as already used
    instead of allowing an unprotected write.
    """

    if token in (None, ""):
        return SubmissionResult(executed=True, value=operation())
    try:
        normalized_token = UUID(str(token))
    except (TypeError, ValueError, AttributeError):
        return SubmissionResult(executed=False)

    with transaction.atomic():
        try:
            with transaction.atomic():
                FormSubmissionModel.objects.create(
                    farm=farm,
                    user=user,
                    scope=scope,
                    token=normalized_token,
                )
        except IntegrityError:
            return SubmissionResult(executed=False)
        return SubmissionResult(executed=True, value=operation())
