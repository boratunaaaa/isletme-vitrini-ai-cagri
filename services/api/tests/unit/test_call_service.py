from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.call import Call, CallEvent
from app.models.enums import CallOutcome, CallStatus
from app.models.lead import Lead
from app.services import call_service
from app.services.call_service import (
    derive_fallback_outcome,
    finalize_outcome,
    get_call_or_none,
    record_event,
    transition,
)


def _call(db_session, *, status: CallStatus = CallStatus.QUEUED) -> Call:
    lead = Lead(business_name="Call Service Lead")
    db_session.add(lead)
    db_session.flush()
    call = Call(lead_id=lead.id, status=status.value)
    db_session.add(call)
    db_session.flush()
    return call


def test_record_event_publishes_safe_payload(
    db_session,
    clean_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[dict] = []
    monkeypatch.setattr(call_service, "publish_event", published.append)
    call = _call(db_session)

    event = record_event(db_session, call, "queued", {"safe": True})

    assert event.event_type == "queued"
    assert published[0]["payload"] == {"safe": True}
    assert published[0]["lead_id"] == str(call.lead_id)


def test_transition_sets_timestamps_duration_and_reason(
    db_session,
    clean_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(call_service, "publish_event", lambda payload: None)
    call = _call(db_session)

    transition(db_session, call, CallStatus.PREPARING)
    transition(db_session, call, CallStatus.DIALING)
    assert call.started_at is not None
    transition(db_session, call, CallStatus.RINGING)
    transition(db_session, call, CallStatus.ANSWERED)
    call.answered_at = datetime.now(UTC) - timedelta(seconds=5)
    transition(db_session, call, CallStatus.AGENT_ACTIVE)
    transition(db_session, call, CallStatus.COMPLETED, reason="finished")

    assert call.ended_at is not None
    assert call.duration_seconds is not None and call.duration_seconds >= 0
    assert call.disconnect_reason == "finished"


def test_finalize_outcome_is_idempotent_and_records_flags(
    db_session,
    clean_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(call_service, "publish_event", lambda payload: None)
    call = _call(db_session, status=CallStatus.COMPLETED)
    callback_at = datetime.now(UTC) + timedelta(hours=1)

    finalize_outcome(
        db_session,
        call,
        outcome=CallOutcome.CALLBACK_REQUESTED,
        summary="x" * 5000,
        callback_at=callback_at,
        demo_requested=True,
        transfer_requested=True,
    )
    finalize_outcome(db_session, call, outcome=CallOutcome.WRONG_NUMBER)

    assert call.outcome == CallOutcome.CALLBACK_REQUESTED.value
    assert len(call.safe_summary or "") == 4000
    assert call.callback_at == callback_at
    assert call.demo_requested is True
    assert call.transfer_requested is True


@pytest.mark.parametrize(
    ("event_type", "expected"),
    [
        ("tool:add_to_suppression_list", CallOutcome.DO_NOT_CALL),
        ("tool:mark_wrong_number", CallOutcome.WRONG_NUMBER),
        ("tool:request_demo_link", CallOutcome.DEMO_REQUESTED),
        ("tool:schedule_callback", CallOutcome.CALLBACK_REQUESTED),
        ("tool:request_human_transfer", CallOutcome.TRANSFERRED_TO_HUMAN),
        ("tool:mark_not_interested", CallOutcome.NOT_INTERESTED),
        ("tool:mark_interested", CallOutcome.INTERESTED),
        ("tool:mark_decision_maker_unavailable", CallOutcome.DECISION_MAKER_UNAVAILABLE),
    ],
)
def test_derive_fallback_outcome_prefers_tool_events(
    db_session,
    clean_db,
    event_type: str,
    expected: CallOutcome,
) -> None:
    call = _call(db_session, status=CallStatus.FAILED)
    db_session.add(
        CallEvent(call_id=call.id, event_type=event_type, event_timestamp=datetime.now(UTC))
    )
    db_session.flush()

    assert derive_fallback_outcome(db_session, call) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (CallStatus.NO_ANSWER, CallOutcome.NO_ANSWER),
        (CallStatus.BUSY, CallOutcome.NO_ANSWER),
        (CallStatus.VOICEMAIL, CallOutcome.VOICEMAIL),
        (CallStatus.REJECTED, CallOutcome.NO_ANSWER),
        (CallStatus.FAILED, CallOutcome.TECHNICAL_FAILURE),
        (CallStatus.CANCELLED, CallOutcome.TECHNICAL_FAILURE),
    ],
)
def test_derive_fallback_outcome_from_status(
    db_session,
    clean_db,
    status: CallStatus,
    expected: CallOutcome,
) -> None:
    call = _call(db_session, status=status)

    assert derive_fallback_outcome(db_session, call) == expected


def test_derive_fallback_existing_answered_and_default_paths(db_session, clean_db) -> None:
    existing = _call(db_session, status=CallStatus.COMPLETED)
    existing.outcome = CallOutcome.INTERESTED.value
    answered = _call(db_session, status=CallStatus.AGENT_ACTIVE)
    answered.answered_at = datetime.now(UTC)
    unknown = _call(db_session, status=CallStatus.QUEUED)

    assert derive_fallback_outcome(db_session, existing) == CallOutcome.INTERESTED
    assert derive_fallback_outcome(db_session, answered) == CallOutcome.FOLLOW_UP_REQUIRED
    assert derive_fallback_outcome(db_session, unknown) == CallOutcome.TECHNICAL_FAILURE
    assert get_call_or_none(db_session, existing.id) == existing
