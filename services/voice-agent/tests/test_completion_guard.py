from __future__ import annotations

import asyncio
import uuid

import pytest

from agent.api_client import DuplicateConflictError
from agent.errors import (
    CallNotDialableError,
    CompletionError,
    InternalAPIAuthenticationError,
    InternalAPIPermanentError,
    InternalAPITransientError,
)
from agent.job_handler import CompletionGuard
from agent.models import CompletionIn, DisconnectReason, GenericAcceptedResponse


class _RecordingAPI:
    def __init__(
        self,
        *,
        fail_times: int = 0,
        fail_with: type[Exception] = InternalAPITransientError,
        yield_before_append: bool = False,
    ) -> None:
        self.calls: list[CompletionIn] = []
        self.all_attempts: list[CompletionIn] = []
        self.attempts = 0
        self._fail_times = fail_times
        self._fail_with = fail_with
        self._yield_before_append = yield_before_append

    async def complete(
        self, call_id: uuid.UUID, completion: CompletionIn
    ) -> GenericAcceptedResponse:
        self.attempts += 1
        self.all_attempts.append(completion)
        if self._yield_before_append:
            await asyncio.sleep(0.01)  # gerçek bir yield noktası — yarışı mümkün kılar
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._fail_with("simulated failure")
        self.calls.append(completion)
        return GenericAcceptedResponse(status="completed")


class _AlwaysFailingAPI:
    def __init__(self, *, fail_with: type[Exception] = InternalAPITransientError) -> None:
        self.attempts = 0
        self._fail_with = fail_with

    async def complete(
        self, call_id: uuid.UUID, completion: CompletionIn
    ) -> GenericAcceptedResponse:
        self.attempts += 1
        raise self._fail_with("backend down")


@pytest.mark.asyncio
async def test_completion_sent_exactly_once_on_success() -> None:
    api = _RecordingAPI()
    guard = CompletionGuard()
    call_id = uuid.uuid4()

    await guard.complete_once(
        api=api, call_id=call_id, started_monotonic=0.0, reason=DisconnectReason.COMPLETED
    )
    await guard.complete_once(
        api=api, call_id=call_id, started_monotonic=0.0, reason=DisconnectReason.AGENT_ERROR
    )

    assert len(api.calls) == 1
    assert guard.completed is True


@pytest.mark.asyncio
async def test_retries_transient_failures_then_succeeds() -> None:
    api = _RecordingAPI(fail_times=2, fail_with=InternalAPITransientError)
    guard = CompletionGuard(max_attempts=3)

    await guard.complete_once(
        api=api, call_id=uuid.uuid4(), started_monotonic=0.0, reason=DisconnectReason.COMPLETED
    )

    assert len(api.calls) == 1
    assert api.attempts == 3  # 2 başarısız + 1 başarılı deneme
    assert guard.completed is True


@pytest.mark.asyncio
async def test_transient_exhausted_retries_raise_and_do_not_mark_completed() -> None:
    """KRİTİK regresyon testi: eski davranışta `_completed` API çağrısından
    ÖNCE set ediliyordu, bu yüzden başarısızlık sessizce yutuluyordu
    (bkz. CLAUDE_AUDIT_PHASE_4.md YÜKSEK-1). Bu test tam o senaryoyu kapatır:
    tüm GEÇİCİ hata denemeleri başarısız olursa guard `completed=False`
    kalmalı ve `CompletionError` fırlatmalı — sessiz yutma yok."""
    api = _AlwaysFailingAPI(fail_with=InternalAPITransientError)
    guard = CompletionGuard(max_attempts=3)

    with pytest.raises(CompletionError):
        await guard.complete_once(
            api=api, call_id=uuid.uuid4(), started_monotonic=0.0, reason=DisconnectReason.COMPLETED
        )

    assert api.attempts == 3
    assert guard.completed is False


@pytest.mark.asyncio
async def test_second_call_after_exhaustion_does_not_retry_again() -> None:
    api = _AlwaysFailingAPI(fail_with=InternalAPITransientError)
    guard = CompletionGuard(max_attempts=2)

    with pytest.raises(CompletionError):
        await guard.complete_once(
            api=api, call_id=uuid.uuid4(), started_monotonic=0.0, reason=DisconnectReason.COMPLETED
        )
    assert api.attempts == 2

    # İkinci çağrı (job_handler'ın genel except bloğundan gelen) yeniden
    # deneme fırtınası başlatmamalı, sessizce dönmeli.
    await guard.complete_once(
        api=api, call_id=uuid.uuid4(), started_monotonic=0.0, reason=DisconnectReason.AGENT_ERROR
    )
    assert api.attempts == 2


@pytest.mark.asyncio
async def test_concurrent_complete_once_calls_send_single_completion() -> None:
    """İki completion task'ının GERÇEKTEN aynı anda (yield noktasında
    kesişecek şekilde) tetiklendiği yarış senaryosu — ör. remote hangup ile
    end_call_safely aynı anda gerçekleşirse. `asyncio.Lock` olmadan bu test
    iki `api.complete()` çağrısı üretirdi (her iki task da kilit yokken
    `_completed=False` kontrolünü geçip API çağrısına girebilirdi)."""
    api = _RecordingAPI(yield_before_append=True)
    guard = CompletionGuard()
    call_id = uuid.uuid4()

    await asyncio.gather(
        guard.complete_once(
            api=api, call_id=call_id, started_monotonic=0.0, reason=DisconnectReason.REMOTE_HANGUP
        ),
        guard.complete_once(
            api=api, call_id=call_id, started_monotonic=0.0, reason=DisconnectReason.AGENT_HANGUP
        ),
    )

    assert len(api.calls) == 1


# ─── Permanent vs transient sınıflandırması (CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-2) ──


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_type",
    [
        InternalAPIAuthenticationError,  # 401/403
        InternalAPIPermanentError,  # 400/404/422/vb.
        CallNotDialableError,  # 409/4xx CALL_NOT_DIALABLE
        DuplicateConflictError,  # 409 farklı payload
    ],
)
async def test_permanent_errors_are_not_retried(exc_type: type[Exception]) -> None:
    api = _AlwaysFailingAPI(fail_with=exc_type)
    guard = CompletionGuard(max_attempts=3)

    with pytest.raises(CompletionError):
        await guard.complete_once(
            api=api, call_id=uuid.uuid4(), started_monotonic=0.0, reason=DisconnectReason.COMPLETED
        )

    assert api.attempts == 1  # tek deneme, retry yok
    assert guard.completed is False


@pytest.mark.asyncio
async def test_unknown_exception_type_defaults_to_single_attempt() -> None:
    """Sınıflandırılmamış (beklenmeyen) bir exception tipi de güvenli
    varsayılan olarak retry EDİLMEMELİ — 'her hatayı retry et' orijinal
    hatasının aynısını farklı bir exception sınıfıyla tekrarlamamak için."""
    api = _AlwaysFailingAPI(fail_with=RuntimeError)
    guard = CompletionGuard(max_attempts=3)

    with pytest.raises(CompletionError):
        await guard.complete_once(
            api=api, call_id=uuid.uuid4(), started_monotonic=0.0, reason=DisconnectReason.COMPLETED
        )

    assert api.attempts == 1


@pytest.mark.asyncio
async def test_completion_event_id_stable_across_retries() -> None:
    api = _RecordingAPI(fail_times=2, fail_with=InternalAPITransientError)
    guard = CompletionGuard(max_attempts=3)
    call_id = uuid.uuid4()

    await guard.complete_once(
        api=api, call_id=call_id, started_monotonic=0.0, reason=DisconnectReason.COMPLETED
    )

    assert len(api.all_attempts) == 3  # 2 başarısız + 1 başarılı
    ids = {c.completion_event_id for c in api.all_attempts}
    assert ids == {f"completion-{call_id}"}  # tüm denemelerde AYNI ID


@pytest.mark.asyncio
async def test_permanent_error_final_failure_is_logged_not_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    api = _AlwaysFailingAPI(fail_with=InternalAPIAuthenticationError)
    guard = CompletionGuard(max_attempts=3)

    with (
        caplog.at_level(logging.ERROR, logger="agent.job_handler"),
        pytest.raises(CompletionError),
    ):
        await guard.complete_once(
            api=api,
            call_id=uuid.uuid4(),
            started_monotonic=0.0,
            reason=DisconnectReason.COMPLETED,
        )

    assert any("başarısız oldu" in record.message for record in caplog.records)
