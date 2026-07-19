from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import HttpUrl, SecretStr

from agent.api_client import DuplicateConflictError, InternalAPIClient
from agent.config import VoiceAgentSettings
from agent.errors import (
    CallNotDialableError,
    InternalAPIAuthenticationError,
    InternalAPIContractError,
    InternalAPIPermanentError,
    InternalAPITransientError,
)
from agent.models import AgentEventType, LifecycleEventIn


class SequenceTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        response = self.responses.pop(0)
        response.request = request
        return response


def settings() -> VoiceAgentSettings:
    return VoiceAgentSettings(
        INTERNAL_API_BASE_URL=HttpUrl("http://internal.test"),
        INTERNAL_SERVICE_TOKEN=SecretStr("internal-token-value"),
        HTTP_MAX_RETRIES=2,
        HTTP_TIMEOUT_SECONDS=1,
    )


@pytest.mark.asyncio
async def test_bearer_token_added_and_health_validated() -> None:
    transport = SequenceTransport([httpx.Response(200, json={"status": "ok"})])
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    assert await client.health() == {"status": "ok"}

    assert transport.requests[0].headers["Authorization"] == "Bearer internal-token-value"
    await client.aclose()


@pytest.mark.asyncio
async def test_401_not_retried() -> None:
    transport = SequenceTransport(
        [
            httpx.Response(
                401,
                json={
                    "error": {
                        "code": "INTERNAL_AUTH_INVALID",
                        "message": "bad",
                        "request_id": "r",
                    }
                },
            )
        ]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(InternalAPIAuthenticationError):
        await client.health()

    assert len(transport.requests) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_503_retried_then_success() -> None:
    call_id = uuid.uuid4()
    now = datetime.now(UTC)
    transport = SequenceTransport(
        [
            httpx.Response(503, json={"error": {"code": "X", "message": "x", "request_id": "r"}}),
            httpx.Response(200, json={"status": "accepted", "idempotent": False}),
        ]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )
    event = LifecycleEventIn(
        event_id="evt-1",
        event_type=AgentEventType.AGENT_JOB_STARTED,
        occurred_at=now,
        sequence=1,
        payload={"safe": True},
    )

    response = await client.send_event(call_id, event)

    assert response.status == "accepted"
    assert len(transport.requests) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_409_duplicate_conflict_classified() -> None:
    transport = SequenceTransport(
        [
            httpx.Response(
                409,
                json={
                    "error": {
                        "code": "DUPLICATE_EVENT_CONFLICT",
                        "message": "duplicate",
                        "request_id": "r",
                    }
                },
            )
        ]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(DuplicateConflictError):
        await client.health()

    await client.aclose()


@pytest.mark.asyncio
async def test_contract_response_validation() -> None:
    transport = SequenceTransport([httpx.Response(200, json={"unexpected": "shape"})])
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(InternalAPIPermanentError):
        await client.bootstrap(uuid.uuid4())
    # InternalAPIPermanentError bir InternalAPIContractError alt sınıfıdır —
    # eski genel `except InternalAPIContractError` çağıranlar hâlâ yakalar.
    assert issubclass(InternalAPIPermanentError, InternalAPIContractError)

    await client.aclose()


# ─── Permanent vs transient HTTP hata sınıflandırması ─────────────────────────
#
# CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-2: CompletionGuard tüm hataları retry
# ediyordu. Bu, gerçek sınıflandırmanın `api_client.py` seviyesinde net
# olmasını gerektirir; aşağıdaki testler o katmanı doğrudan doğrular.


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 404, 422])
async def test_permanent_4xx_not_retried(status_code: int) -> None:
    transport = SequenceTransport(
        [
            httpx.Response(
                status_code,
                json={"error": {"code": "VALIDATION_ERROR", "message": "bad", "request_id": "r"}},
            )
        ]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(InternalAPIPermanentError):
        await client.health()

    assert len(transport.requests) == 1  # tek deneme, retry yok
    await client.aclose()


@pytest.mark.asyncio
async def test_call_not_dialable_4xx_not_retried() -> None:
    transport = SequenceTransport(
        [
            httpx.Response(
                422,
                json={
                    "error": {
                        "code": "CALL_NOT_DIALABLE",
                        "message": "not dialable",
                        "request_id": "r",
                    }
                },
            )
        ]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(CallNotDialableError):
        await client.health()

    assert len(transport.requests) == 1
    await client.aclose()


@pytest.mark.asyncio
async def test_429_retried_with_retry_after_then_success() -> None:
    transport = SequenceTransport(
        [
            httpx.Response(429, headers={"Retry-After": "0"}, json={}),
            httpx.Response(200, json={"status": "accepted", "idempotent": False}),
        ]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    response = await client.health()

    assert response == {"status": "accepted", "idempotent": False}
    assert len(transport.requests) == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_429_exhausted_retries_raise_transient_error() -> None:
    transport = SequenceTransport(
        [httpx.Response(429, headers={"Retry-After": "0"}, json={}) for _ in range(3)]
    )
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(InternalAPITransientError):
        await client.health()

    # HTTP_MAX_RETRIES=2 -> toplam 3 deneme (ilk + 2 retry), sınırsız değil.
    assert len(transport.requests) == 3
    await client.aclose()


@pytest.mark.asyncio
async def test_429_retry_after_capped_at_upper_bound() -> None:
    """`Retry-After` aşırı büyükse (999999s) `HTTP_MAX_RETRY_AFTER_SECONDS`
    ile kırpılmalı. Testte üst sınır küçük bir değere ayarlanır ki test
    gerçek üst sınırı saniyeler içinde doğrulasın (üretimde varsayılan 30s)."""
    import time

    transport = SequenceTransport(
        [
            httpx.Response(429, headers={"Retry-After": "999999"}, json={}),
            httpx.Response(200, json={"status": "accepted", "idempotent": False}),
        ]
    )
    tight_settings = VoiceAgentSettings(
        INTERNAL_API_BASE_URL=HttpUrl("http://internal.test"),
        INTERNAL_SERVICE_TOKEN=SecretStr("internal-token-value"),
        HTTP_MAX_RETRIES=2,
        HTTP_TIMEOUT_SECONDS=1,
        HTTP_MAX_RETRY_AFTER_SECONDS=0.05,
    )
    client = InternalAPIClient(
        tight_settings,
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    started = time.monotonic()
    await client.health()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0  # 999999s Retry-After'ı sonuna kadar beklemedi
    await client.aclose()


@pytest.mark.asyncio
async def test_503_exhausted_retries_raise_transient_error_not_contract_error() -> None:
    transport = SequenceTransport([httpx.Response(503, json={}) for _ in range(3)])
    client = InternalAPIClient(
        settings(),
        httpx.AsyncClient(base_url="http://internal.test/api/internal/v1", transport=transport),
    )

    with pytest.raises(InternalAPITransientError):
        await client.health()

    await client.aclose()


def test_phone_response_not_in_logger_message(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from agent.logging import configure_logging

    configure_logging("INFO")
    logger = logging.getLogger("agent.test")

    logger.warning("dial plan payload %s", {"phone_e164": "+905551112233"})

    assert "+905551112233" not in caplog.text
    assert "[REDACTED_PHONE]" in caplog.text
