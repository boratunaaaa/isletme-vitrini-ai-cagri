"""Çağrı yaşam döngüsü: state machine geçişleri, olay kaydı, sonuçlandırma,
deterministic fallback sınıflandırma."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.call import Call, CallEvent
from app.models.enums import (
    CALL_STATUS_TRANSITIONS,
    TERMINAL_CALL_STATUSES,
    CallOutcome,
    CallStatus,
)
from app.services.event_bus import publish_event

logger = logging.getLogger(__name__)


class InvalidTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Geçersiz durum geçişi: {current} → {target}")
        self.current = current
        self.target = target


def record_event(
    db: Session,
    call: Call,
    event_type: str,
    safe_payload: dict[str, Any] | None = None,
    *,
    publish: bool = True,
) -> CallEvent:
    event = CallEvent(
        call_id=call.id,
        event_type=event_type,
        safe_payload=safe_payload,
        event_timestamp=datetime.now(UTC),
    )
    db.add(event)
    if publish:
        publish_event(
            {
                "type": "call_event",
                "event_type": event_type,
                "call_id": str(call.id),
                "lead_id": str(call.lead_id),
                "campaign_id": str(call.campaign_id) if call.campaign_id else None,
                "status": call.status,
                "payload": safe_payload or {},
                "ts": event.event_timestamp.isoformat(),
            }
        )
    return event


def transition(
    db: Session,
    call: Call,
    new_status: CallStatus,
    *,
    reason: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Call:
    current = CallStatus(call.status)
    if current == new_status:
        return call
    allowed = CALL_STATUS_TRANSITIONS.get(current, frozenset())
    if new_status not in allowed:
        raise InvalidTransition(current.value, new_status.value)

    call.status = new_status.value
    now = datetime.now(UTC)
    if new_status == CallStatus.DIALING and call.started_at is None:
        call.started_at = now
    if new_status == CallStatus.ANSWERED and call.answered_at is None:
        call.answered_at = now
    if new_status in TERMINAL_CALL_STATUSES:
        call.ended_at = now
        if call.answered_at is not None:
            call.duration_seconds = max(int((now - call.answered_at).total_seconds()), 0)
        if reason:
            call.disconnect_reason = reason[:255]

    record_event(
        db,
        call,
        f"status:{new_status.value}",
        {**(payload or {}), **({"reason": reason} if reason else {})},
    )
    return call


def finalize_outcome(
    db: Session,
    call: Call,
    *,
    outcome: CallOutcome,
    summary: str | None = None,
    callback_at: datetime | None = None,
    demo_requested: bool = False,
    transfer_requested: bool = False,
) -> Call:
    """Idempotent sonuç yazımı: outcome bir kez yazılır, sonraki çağrılar no-op."""
    if call.outcome is not None:
        return call
    call.outcome = outcome.value
    if summary:
        call.safe_summary = summary[:4000]
    if callback_at is not None:
        call.callback_at = callback_at
    call.demo_requested = call.demo_requested or demo_requested
    call.transfer_requested = call.transfer_requested or transfer_requested
    record_event(db, call, "outcome_finalized", {"outcome": outcome.value})
    return call


# ─── Deterministic fallback sınıflandırma (bölüm 27) ─────────────────────────

_STATUS_FALLBACK: dict[str, CallOutcome] = {
    CallStatus.NO_ANSWER.value: CallOutcome.NO_ANSWER,
    CallStatus.BUSY.value: CallOutcome.NO_ANSWER,
    CallStatus.VOICEMAIL.value: CallOutcome.VOICEMAIL,
    CallStatus.REJECTED.value: CallOutcome.NO_ANSWER,
    CallStatus.FAILED.value: CallOutcome.TECHNICAL_FAILURE,
    CallStatus.CANCELLED.value: CallOutcome.TECHNICAL_FAILURE,
}


def derive_fallback_outcome(db: Session, call: Call) -> CallOutcome:
    """Realtime oturum sonuç üretemeden koptuysa: son durum + tool geçmişi +
    event geçmişinden deterministik sonuç. Ek API çağrısı YAPILMAZ."""
    if call.outcome is not None:
        return CallOutcome(call.outcome)

    event_types = set(
        db.scalars(select(CallEvent.event_type).where(CallEvent.call_id == call.id)).all()
    )
    if "tool:add_to_suppression_list" in event_types:
        return CallOutcome.DO_NOT_CALL
    if "tool:mark_wrong_number" in event_types:
        return CallOutcome.WRONG_NUMBER
    if "tool:request_demo_link" in event_types:
        return CallOutcome.DEMO_REQUESTED
    if "tool:schedule_callback" in event_types:
        return CallOutcome.CALLBACK_REQUESTED
    if "tool:request_human_transfer" in event_types:
        return CallOutcome.TRANSFERRED_TO_HUMAN
    if "tool:mark_not_interested" in event_types:
        return CallOutcome.NOT_INTERESTED
    if "tool:mark_interested" in event_types:
        return CallOutcome.INTERESTED
    if "tool:mark_decision_maker_unavailable" in event_types:
        return CallOutcome.DECISION_MAKER_UNAVAILABLE

    mapped = _STATUS_FALLBACK.get(call.status)
    if mapped is not None:
        return mapped
    if call.answered_at is not None:
        return CallOutcome.FOLLOW_UP_REQUIRED  # konuşma oldu ama sonuçsuz koptu
    return CallOutcome.TECHNICAL_FAILURE


def get_call_or_none(db: Session, call_id: uuid.UUID) -> Call | None:
    return db.get(Call, call_id)
