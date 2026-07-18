from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import SuppressionEntry


def is_suppressed(db: Session, phone_hash: str) -> bool:
    return (
        db.scalar(
            select(SuppressionEntry.id).where(SuppressionEntry.phone_hash == phone_hash).limit(1)
        )
        is not None
    )


def add_suppression(
    db: Session,
    *,
    phone_hash: str,
    phone_last_four: str,
    reason: str,
    source: str,
    lead_id: uuid.UUID | None = None,
    added_by: uuid.UUID | None = None,
) -> SuppressionEntry:
    """Idempotent: aynı phone_hash için var olan kayıt döner."""
    existing = db.scalars(
        select(SuppressionEntry).where(SuppressionEntry.phone_hash == phone_hash)
    ).first()
    if existing is not None:
        return existing
    entry = SuppressionEntry(
        phone_hash=phone_hash,
        phone_last_four=phone_last_four,
        reason=reason[:255],
        source=source,
        lead_id=lead_id,
        added_by=added_by,
    )
    db.add(entry)
    db.flush()
    return entry


def remove_suppression(db: Session, entry_id: uuid.UUID) -> bool:
    entry = db.get(SuppressionEntry, entry_id)
    if entry is None:
        return False
    db.delete(entry)
    return True
