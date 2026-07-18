"""Kullanım (usage) raporlama.

Gerçek `AgentSession.usage` özelliği `AgentSessionUsage(model_usage: list[ModelUsage])`
döndürür (bkz. `.venv/lib/python3.11/site-packages/livekit/agents/metrics/usage.py`,
`ModelUsageCollector`). Realtime modeller `LLMModelUsage` olarak toplanır — alan
adları backend'in `UsageUpdateIn` şemasıyla BİREBİR AYNI DEĞİL (ör. SDK
`input_cached_audio_tokens` derken bizim şemamız `cached_input_audio_tokens`
kullanıyor); bu modül yalnız gerçekten var olan alanları doğru eşleyerek okur,
SDK'nın sağlamadığı hiçbir alanı (ör. `reasoning_tokens`) uydurmaz.

Usage yalnız görüşme SONUNDA (final) okunur — bu SDK sürümünde `AgentSession`
kaynağında canlı/incremental bir "session_usage_updated" emit noktası
doğrulanamadı (yalnız event tipi tanımlı, hiç tetiklenmiyor); bu yüzden
incremental raporlama uydurulmadı, yalnız güvenilir final anlık görüntü
kullanılıyor.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from agent.api_client import InternalAPIClient
from agent.models import UsageSourceIn, UsageUpdateIn

logger = logging.getLogger(__name__)


class UsageSink(Protocol):
    async def send_usage(self, usage: UsageUpdateIn) -> None: ...

    async def report_unavailable(self, *, model: str, is_final: bool) -> str: ...


class ProviderUsageSink:
    def __init__(self, *, call_id: uuid.UUID, api: InternalAPIClient) -> None:
        self._call_id = call_id
        self._api = api
        self._sent_ids: set[str] = set()

    async def send_usage(self, usage: UsageUpdateIn) -> None:
        if usage.usage_event_id in self._sent_ids:
            return
        self._sent_ids.add(usage.usage_event_id)
        await self._api.send_usage(self._call_id, usage)

    async def report_unavailable(self, *, model: str, is_final: bool) -> str:
        event_id = f"usage-unavailable-{uuid.uuid4().hex[:16]}"
        await self.send_usage(
            UsageUpdateIn(
                usage_event_id=event_id,
                provider="openai",
                model=model,
                occurred_at=datetime.now(UTC),
                is_final=is_final,
                usage_source=UsageSourceIn.UNAVAILABLE,
            )
        )
        return event_id


def usage_from_session(session: Any, *, model: str, is_final: bool = True) -> UsageUpdateIn | None:
    """`AgentSession.usage.model_usage` içindeki gerçek LLM (Realtime) kullanım
    kaydını okur. Session hiç `usage` sağlamıyorsa veya LLM kaydı yoksa `None`
    döner (çağıran taraf bu durumda `report_unavailable()`'a düşmeli)."""
    usage_obj = getattr(session, "usage", None)
    model_usage = getattr(usage_obj, "model_usage", None)
    if not model_usage:
        return None

    llm_usage = next(
        (u for u in model_usage if getattr(u, "type", None) == "llm_usage"),
        None,
    )
    if llm_usage is None:
        return None

    def field(name: str, default: int = 0) -> int:
        value = getattr(llm_usage, name, default)
        return int(value or 0)

    return UsageUpdateIn(
        usage_event_id=f"usage-final-{uuid.uuid4().hex[:16]}",
        provider="openai",
        model=model,
        input_audio_tokens=field("input_audio_tokens"),
        cached_input_audio_tokens=field("input_cached_audio_tokens"),
        output_audio_tokens=field("output_audio_tokens"),
        input_text_tokens=field("input_text_tokens"),
        cached_input_text_tokens=field("input_cached_text_tokens"),
        output_text_tokens=field("output_text_tokens"),
        reasoning_tokens=None,  # SDK bu alanı sağlamıyor; uydurulmaz.
        is_final=is_final,
        occurred_at=datetime.now(UTC),
        usage_source=UsageSourceIn.PROVIDER_REPORTED,
    )


class MemoryUsageSink:
    def __init__(self) -> None:
        self.usages: list[UsageUpdateIn] = []

    async def send_usage(self, usage: UsageUpdateIn) -> None:
        if all(existing.usage_event_id != usage.usage_event_id for existing in self.usages):
            self.usages.append(usage)

    async def report_unavailable(self, *, model: str, is_final: bool) -> str:
        event_id = f"usage-unavailable-{uuid.uuid4().hex[:16]}"
        await self.send_usage(
            UsageUpdateIn(
                usage_event_id=event_id,
                provider="openai",
                model=model,
                occurred_at=datetime.now(UTC),
                is_final=is_final,
                usage_source=UsageSourceIn.UNAVAILABLE,
            )
        )
        return event_id
