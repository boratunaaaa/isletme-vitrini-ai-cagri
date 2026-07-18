from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.system import AuditLog


def write_audit(
    db: Session,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    safe_metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Audit kaydı. safe_metadata içine PII/secret koymak çağıranın ihlalidir;
    yine de savunma amaçlı bilinen alan adları süzülür."""
    if safe_metadata:
        safe_metadata = {
            k: v
            for k, v in safe_metadata.items()
            if k.lower() not in {"phone", "password", "token", "secret", "api_key", "authorization"}
        }
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            safe_metadata=safe_metadata,
            ip_address=ip_address,
        )
    )
