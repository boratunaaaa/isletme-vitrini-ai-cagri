from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.internal import InternalInvocation

T = TypeVar("T")

_PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SECRET_KEYS = {
    "authorization",
    "token",
    "api_key",
    "api_secret",
    "password",
    "secret",
    "phone",
    "phone_e164",
    "transcript",
    "audio",
}


def canonical_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def redact_text(value: str) -> str:
    value = _EMAIL_RE.sub("[redacted-email]", value)
    return _PHONE_RE.sub("[redacted-phone]", value)


def sanitize_payload(payload: dict[str, Any], *, max_bytes: int = 4096) -> dict[str, Any]:
    sanitized = _sanitize(payload)
    encoded = json.dumps(sanitized, ensure_ascii=False, default=str).encode("utf-8")
    if len(encoded) > max_bytes:
        return {"truncated": True, "size_bytes": len(encoded)}
    return sanitized


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in _SECRET_KEYS:
                result[key_text] = "[redacted]"
            else:
                result[key_text] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:50]]
    if isinstance(value, str):
        return redact_text(value[:1000])
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


class IdempotencyConflict(Exception):
    pass


def idempotent(
    db: Session,
    *,
    call_id: uuid.UUID,
    external_id: str,
    event_type: str,
    payload: Any,
    handler: Callable[[], T],
) -> tuple[T, bool]:
    hash_payload = sanitize_payload(payload) if isinstance(payload, dict) else payload
    payload_hash = canonical_hash(hash_payload)
    existing = db.scalars(
        select(InternalInvocation).where(
            InternalInvocation.call_id == call_id,
            InternalInvocation.external_id == external_id,
        )
    ).first()
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise IdempotencyConflict(external_id)
        return existing.result_snapshot, True  # type: ignore[return-value]

    result = handler()
    db.add(
        InternalInvocation(
            call_id=call_id,
            external_id=external_id,
            event_type=event_type,
            payload_hash=payload_hash,
            processing_status="processed",
            result_snapshot=result if isinstance(result, dict) else {"result": result},
            processed_at=datetime.now(UTC),
        )
    )
    db.flush()
    return result, False
