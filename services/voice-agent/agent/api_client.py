from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from agent.config import VoiceAgentSettings
from agent.errors import (
    CallNotDialableError,
    InternalAPIAuthenticationError,
    InternalAPIContractError,
    InternalAPIPermanentError,
    InternalAPITransientError,
)
from agent.models import (
    BootstrapResponse,
    CompletionIn,
    DialPlanResponse,
    GenericAcceptedResponse,
    InternalErrorResponse,
    LifecycleEventIn,
    ToolResponse,
    TranscriptTurnIn,
    UsageResponse,
    UsageUpdateIn,
)
from agent.redaction import safe_error_message, safe_value

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

DEFAULT_RATE_LIMIT_RETRY_SECONDS = 1.0


class DuplicateConflictError(InternalAPIContractError):
    """409 DUPLICATE_EVENT_CONFLICT (aynı ID, farklı payload) — KALICI hata.
    Aynı payload'la retry yalnız gürültü üretir, sonucu değiştirmez."""


class _RateLimitedSignal(Exception):  # noqa: N818 - dahili kontrol sinyali, hata değil
    """`_handle_response()`'dan `_request()`'in retry döngüsüne 429 +
    `Retry-After` bilgisini taşımak için kullanılan modül-içi sinyal.
    Dışarı asla sızmaz; `_request()` içinde daima yakalanır."""

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limited, retry after {retry_after_seconds}s")


@dataclass(frozen=True)
class InternalAPIResult:
    status_code: int
    payload: dict[str, Any]


def _parse_retry_after(headers: Mapping[str, str], *, upper_bound: float) -> float:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return DEFAULT_RATE_LIMIT_RETRY_SECONDS
    try:
        seconds = float(raw)
    except ValueError:
        return DEFAULT_RATE_LIMIT_RETRY_SECONDS
    if seconds < 0:
        return DEFAULT_RATE_LIMIT_RETRY_SECONDS
    return min(seconds, upper_bound)


class InternalAPIClient:
    def __init__(
        self,
        settings: VoiceAgentSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.internal_api_prefix,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": f"{settings.VOICE_AGENT_NAME}/0.1.0"},
        )

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health", response_model=None)

    async def bootstrap(self, call_id: uuid.UUID) -> BootstrapResponse:
        return cast(
            BootstrapResponse,
            await self._request("GET", f"/calls/{call_id}/bootstrap", BootstrapResponse),
        )

    async def dial_plan(self, call_id: uuid.UUID) -> DialPlanResponse:
        return cast(
            DialPlanResponse,
            await self._request("GET", f"/calls/{call_id}/dial-plan", DialPlanResponse),
        )

    async def send_event(
        self,
        call_id: uuid.UUID,
        event: LifecycleEventIn,
    ) -> GenericAcceptedResponse:
        return cast(
            GenericAcceptedResponse,
            await self._request(
                "POST",
                f"/calls/{call_id}/events",
                GenericAcceptedResponse,
                json=event.model_dump(mode="json"),
            ),
        )

    async def send_transcript_turn(
        self, call_id: uuid.UUID, turn: TranscriptTurnIn
    ) -> GenericAcceptedResponse:
        return cast(
            GenericAcceptedResponse,
            await self._request(
                "POST",
                f"/calls/{call_id}/transcript-turns",
                GenericAcceptedResponse,
                json=turn.model_dump(mode="json"),
            ),
        )

    async def send_usage(self, call_id: uuid.UUID, usage: UsageUpdateIn) -> UsageResponse:
        return cast(
            UsageResponse,
            await self._request(
                "POST",
                f"/calls/{call_id}/usage",
                UsageResponse,
                json=usage.model_dump(mode="json"),
            ),
        )

    async def complete(
        self,
        call_id: uuid.UUID,
        completion: CompletionIn,
    ) -> GenericAcceptedResponse:
        return cast(
            GenericAcceptedResponse,
            await self._request(
                "POST",
                f"/calls/{call_id}/complete",
                GenericAcceptedResponse,
                json=completion.model_dump(mode="json"),
            ),
        )

    async def call_tool(
        self, call_id: uuid.UUID, backend_path: str, payload: Mapping[str, Any]
    ) -> ToolResponse:
        return cast(
            ToolResponse,
            await self._request(
                "POST",
                f"/calls/{call_id}/tools/{backend_path}",
                ToolResponse,
                json=dict(payload),
            ),
        )

    async def _request(
        self,
        method: str,
        path: str,
        response_model: type[T] | None,
        *,
        json: dict[str, Any] | None = None,
    ) -> T | dict[str, Any]:
        """HTTP çağrısını yapar; yalnız GERÇEKTEN geçici (network timeout,
        connection reset, 429, 5xx) hatalarda burada retry eder. Kalıcı
        hatalar (401/403/404/409-conflict/422/vb.) `InternalAPIAuthenticationError`,
        `CallNotDialableError`, `DuplicateConflictError` veya
        `InternalAPIPermanentError` olarak İLK denemede fırlatılır ve retry
        edilmez. Tüm geçici deneme bütçesi tükenirse `InternalAPITransientError`
        fırlatılır — üst katmanlar (ör. `CompletionGuard`) bunu ayrı, daha uzun
        vadeli bir retry penceresiyle ele alabilir."""
        headers = {
            "Authorization": f"Bearer {self._settings.internal_token}",
            "X-Request-ID": f"voice-agent-{uuid.uuid4()}",
            "X-Internal-Service-Name": self._settings.INTERNAL_SERVICE_NAME,
        }
        attempts = max(self._settings.HTTP_MAX_RETRIES, 0) + 1
        last_error: BaseException | None = None
        for attempt in range(attempts):
            try:
                response = await self._client.request(method, path, headers=headers, json=json)
                return self._handle_response(response, response_model)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                await asyncio.sleep(min(2**attempt * 0.2, 2.0))
            except _RateLimitedSignal as exc:
                last_error = exc
                if attempt >= attempts - 1:
                    break
                backoff = min(2**attempt * 0.2, 2.0)
                await asyncio.sleep(max(backoff, exc.retry_after_seconds))
            except (
                InternalAPIAuthenticationError,
                CallNotDialableError,
                DuplicateConflictError,
                InternalAPIPermanentError,
            ):
                raise
        message = safe_error_message(last_error or RuntimeError("internal api request failed"))
        raise InternalAPITransientError(f"Internal API request failed: {message}")

    def _handle_response(
        self,
        response: httpx.Response,
        response_model: type[T] | None,
    ) -> T | dict[str, Any]:
        if response.status_code in {401, 403}:
            raise InternalAPIAuthenticationError("Internal API authentication failed.")
        if response.status_code == 429:
            raise _RateLimitedSignal(
                _parse_retry_after(
                    response.headers, upper_bound=self._settings.HTTP_MAX_RETRY_AFTER_SECONDS
                )
            )
        payload = self._json_payload(response)
        if response.status_code == 409:
            error_code = self._error_code(payload)
            if error_code == "DUPLICATE_EVENT_CONFLICT":
                raise DuplicateConflictError("Duplicate idempotency key with conflicting payload.")
            if error_code == "CALL_NOT_DIALABLE":
                raise CallNotDialableError("Call is not dialable.")
            # Sınıflandırılamayan 409 de kalıcıdır — aynı payload'la retry
            # aynı çakışmayı üretir.
            raise InternalAPIPermanentError(f"Internal API conflict: {error_code or 'unknown'}")
        if 400 <= response.status_code < 500:
            error_code = self._error_code(payload)
            if error_code == "CALL_NOT_DIALABLE":
                raise CallNotDialableError("Call is not dialable.")
            # 400/404/422/vb. — kalıcı sözleşme reddi, retry edilmez.
            raise InternalAPIPermanentError(
                f"Internal API rejected request: {error_code or response.status_code}"
            )
        if response.status_code >= 500:
            raise httpx.TransportError(f"temporary server error {response.status_code}")
        if response_model is None:
            if isinstance(payload, dict):
                return payload
            raise InternalAPIPermanentError("Internal API returned non-object JSON.")
        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            logger.warning("Internal API response validation failed: %s", safe_error_message(exc))
            # Şema uyumsuzluğu kalıcıdır (kod/deploy hatası); aynı isteği
            # tekrarlamak sonucu değiştirmez.
            raise InternalAPIPermanentError(
                "Internal API response does not match contract."
            ) from exc

    @staticmethod
    def _json_payload(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise InternalAPIPermanentError("Internal API returned invalid JSON.") from exc

    @staticmethod
    def _error_code(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        try:
            return InternalErrorResponse.model_validate(payload).error.code
        except ValidationError:
            logger.debug("Unrecognized error payload: %s", safe_value(payload))
            return None
