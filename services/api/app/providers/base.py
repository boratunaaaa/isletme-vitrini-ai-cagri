"""Provider protokolleri ve veri tipleri.

Domain katmanı bu protokollere bağımlıdır; hiçbir SDK tipi domain'e sızmaz.
ConversationEngineProvider çalışma zamanı implementasyonu voice-agent
servisindedir (services/voice-agent/agent/engines) — API tarafı yalnız motor
seçimini doğrular (app/providers/conversation.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

# ─── Telephony ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OutboundCallRequest:
    call_id: str
    room_name: str
    phone_e164: str  # yalnız bellekte; loglanmaz, persist edilmez
    trunk_id: str
    agent_name: str
    max_duration_seconds: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelephonyCall:
    provider_call_id: str
    room_name: str


@dataclass(frozen=True)
class TelephonyCallStatus:
    provider_call_id: str
    state: str  # provider'a özgü ham durum
    detail: str | None = None


class TelephonyProvider(Protocol):
    async def create_outbound_call(self, request: OutboundCallRequest) -> TelephonyCall: ...

    async def hangup_call(self, call_id: str) -> None: ...

    async def transfer_call(self, call_id: str, target: str) -> None: ...

    async def get_call_status(self, call_id: str) -> TelephonyCallStatus: ...


# ─── Places ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlaceResult:
    external_place_id: str
    business_name: str
    phone_raw: str | None
    website: str | None
    address: str | None
    category: str | None
    rating: float | None
    review_count: int | None
    city: str | None = None
    district: str | None = None


class PlacesProvider(Protocol):
    async def search_text(
        self, query: str, *, max_results: int = 20
    ) -> list[PlaceResult]: ...

    async def get_place_details(self, place_id: str) -> PlaceResult | None: ...


# ─── Notification ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NotificationMessage:
    kind: str  # demo_request | callback_due | call_result | system
    title: str
    body: str
    resource_type: str | None = None
    resource_id: str | None = None
    created_at: datetime | None = None


class NotificationProvider(Protocol):
    async def notify(self, message: NotificationMessage) -> None: ...
