from __future__ import annotations

from uuid import UUID

import pytest

from app.models.call import Call
from app.models.enums import CALL_STATUS_TRANSITIONS, CallStatus
from app.services import call_service
from app.services.call_service import InvalidTransition, transition


@pytest.fixture(autouse=True)
def no_event_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(call_service, "publish_event", lambda payload: None)
    monkeypatch.setattr(call_service, "record_event", lambda *args, **kwargs: None)


def _call() -> Call:
    return Call(lead_id=UUID("00000000-0000-0000-0000-000000000001"))


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (CallStatus.QUEUED, CallStatus.PREPARING),
        (CallStatus.PREPARING, CallStatus.DIALING),
        (CallStatus.DIALING, CallStatus.RINGING),
        (CallStatus.RINGING, CallStatus.ANSWERED),
        (CallStatus.ANSWERED, CallStatus.AGENT_ACTIVE),
        (CallStatus.AGENT_ACTIVE, CallStatus.COMPLETED),
        (CallStatus.DIALING, CallStatus.FAILED),
        (CallStatus.RINGING, CallStatus.NO_ANSWER),
        (CallStatus.RINGING, CallStatus.BUSY),
    ],
)
def test_allowed_transitions_update_status(
    db_session,
    current: CallStatus,
    target: CallStatus,
) -> None:
    call = _call()
    call.status = current.value

    transition(db_session, call, target, reason="safe_reason")

    assert call.status == target.value


def test_cancelled_transitions_match_declared_table(db_session) -> None:
    cancellable = [
        status
        for status, targets in CALL_STATUS_TRANSITIONS.items()
        if CallStatus.CANCELLED in targets
    ]
    assert cancellable == [
        CallStatus.QUEUED,
        CallStatus.PREPARING,
        CallStatus.DIALING,
        CallStatus.RINGING,
    ]

    for current in cancellable:
        call = _call()
        call.status = current.value
        transition(db_session, call, CallStatus.CANCELLED)
        assert call.status == CallStatus.CANCELLED.value


def test_terminal_and_invalid_transitions_are_rejected_without_pii(db_session) -> None:
    call = _call()
    call.status = CallStatus.COMPLETED.value

    with pytest.raises(InvalidTransition) as exc:
        transition(db_session, call, CallStatus.DIALING, reason="+905321234567")

    assert "+905321234567" not in str(exc.value)


def test_same_status_transition_is_noop(db_session) -> None:
    call = _call()
    call.status = CallStatus.DIALING.value

    assert transition(db_session, call, CallStatus.DIALING) is call
    assert call.status == CallStatus.DIALING.value
