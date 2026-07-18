from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.enums import CallOutcome, CallStatus
from app.services.call_policy import compute_next_retry


def test_retry_delays_by_status() -> None:
    busy = compute_next_retry(
        call_status=CallStatus.BUSY.value,
        outcome=None,
        attempt_count=1,
        max_retry_count=2,
        retry_delay_minutes=120,
    )
    no_answer = compute_next_retry(
        call_status=CallStatus.NO_ANSWER.value,
        outcome=None,
        attempt_count=1,
        max_retry_count=2,
        retry_delay_minutes=120,
    )
    voicemail = compute_next_retry(
        call_status=CallStatus.VOICEMAIL.value,
        outcome=None,
        attempt_count=1,
        max_retry_count=2,
        retry_delay_minutes=120,
    )

    assert busy is not None and no_answer is not None and voicemail is not None
    assert timedelta(minutes=55) < busy - datetime.now(UTC) < timedelta(minutes=65)
    assert timedelta(minutes=115) < no_answer - datetime.now(UTC) < timedelta(minutes=125)
    assert timedelta(minutes=235) < voicemail - datetime.now(UTC) < timedelta(minutes=245)


def test_retry_stops_at_max_and_for_terminal_outcomes() -> None:
    assert (
        compute_next_retry(
            call_status=CallStatus.NO_ANSWER.value,
            outcome=None,
            attempt_count=3,
            max_retry_count=2,
            retry_delay_minutes=120,
        )
        is None
    )
    for outcome in (
        CallOutcome.WRONG_NUMBER.value,
        CallOutcome.DO_NOT_CALL.value,
        CallOutcome.DEMO_REQUESTED.value,
    ):
        assert (
            compute_next_retry(
                call_status=CallStatus.NO_ANSWER.value,
                outcome=outcome,
                attempt_count=1,
                max_retry_count=2,
                retry_delay_minutes=120,
            )
            is None
        )


def test_callback_time_overrides_automatic_retry() -> None:
    callback_at = datetime(2026, 7, 18, 13, 0, tzinfo=UTC)

    assert (
        compute_next_retry(
            call_status=CallStatus.NO_ANSWER.value,
            outcome=CallOutcome.CALLBACK_REQUESTED.value,
            attempt_count=3,
            max_retry_count=0,
            retry_delay_minutes=120,
            callback_at=callback_at,
        )
        == callback_at
    )
