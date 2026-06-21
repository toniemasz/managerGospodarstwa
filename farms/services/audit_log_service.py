from __future__ import annotations

from typing import Any

from farms.models import AuditLogModel


class AuditLogService:
    @staticmethod
    def log(
        *,
        farm,
        user=None,
        action: str,
        obj=None,
        model_label: str | None = None,
        object_id: str | int | None = None,
        object_repr: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLogModel | None:
        if farm is None:
            return None
        if obj is not None:
            model_label = model_label or obj._meta.label
            object_id = object_id if object_id is not None else obj.pk
            object_repr = object_repr if object_repr is not None else str(obj)
        return AuditLogModel.objects.create(
            farm=farm,
            user=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            model_label=model_label or "",
            object_id="" if object_id is None else str(object_id),
            object_repr=(object_repr or "")[:255],
            metadata=metadata or {},
        )


def log_action(**kwargs):
    return AuditLogService.log(**kwargs)
