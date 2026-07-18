"""Konuşma motoru KATALOĞU (API tarafı).

Motorun kendisi voice-agent servisinde koşar; burada yalnız geçerli motor /
model / voice kombinasyonları doğrulanır ve yetki kuralı uygulanır.
Model listeleri kod içine dağıtılmaz; tek kaynak burasıdır ve env ile beslenir.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings
from app.core.rbac import Permission, has_permission
from app.models.enums import ConversationEngine


class EngineValidationError(ValueError):
    pass


@dataclass(frozen=True)
class EngineSelection:
    engine: str
    model: str
    voice: str


REALTIME_VOICES: tuple[str, ...] = (
    "marin",
    "cedar",
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
)


def allowed_models() -> dict[str, list[str]]:
    s = get_settings()
    models: dict[str, list[str]] = {}
    if s.ENABLE_OPENAI_REALTIME:
        models[ConversationEngine.OPENAI_REALTIME.value] = [
            s.OPENAI_REALTIME_DEFAULT_MODEL,
            s.OPENAI_REALTIME_PREMIUM_MODEL,
        ]
    if s.ENABLE_LOCAL_PIPELINE:
        models[ConversationEngine.LOCAL_PIPELINE.value] = ["local-pipeline-v1"]
    models[ConversationEngine.TEST.value] = ["test-conversation-v1"]
    return models


def is_premium_model(model: str) -> bool:
    return model == get_settings().OPENAI_REALTIME_PREMIUM_MODEL


def validate_selection(
    *,
    engine: str | None,
    model: str | None,
    voice: str | None,
    actor_role: str,
    allow_test_engine: bool = False,
) -> EngineSelection:
    s = get_settings()
    engine = engine or s.DEFAULT_CONVERSATION_ENGINE
    catalog = allowed_models()

    if engine == ConversationEngine.TEST.value and not allow_test_engine:
        raise EngineValidationError("Test motoru yalnız otomatik testlerde kullanılabilir")
    if engine not in catalog:
        raise EngineValidationError(f"Konuşma motoru etkin değil: {engine}")

    model = model or (
        s.OPENAI_REALTIME_DEFAULT_MODEL
        if engine == ConversationEngine.OPENAI_REALTIME.value
        else catalog[engine][0]
    )
    if model not in catalog[engine]:
        raise EngineValidationError(f"Model bu motor için geçerli değil: {model}")

    if is_premium_model(model) and not has_permission(actor_role, Permission.PREMIUM_MODEL):
        raise EngineValidationError("Premium model seçimi yalnız owner/admin rollerine açık")

    voice = voice or s.OPENAI_REALTIME_DEFAULT_VOICE
    if engine == ConversationEngine.OPENAI_REALTIME.value and voice not in REALTIME_VOICES:
        raise EngineValidationError(f"Geçersiz voice: {voice}")

    return EngineSelection(engine=engine, model=model, voice=voice)
