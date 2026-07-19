from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from agent.config import VoiceAgentSettings
from agent.errors import ConfigurationError


def test_development_import_allows_missing_runtime_credentials() -> None:
    settings = VoiceAgentSettings(VOICE_AGENT_ENV="development")

    assert "OPENAI_API_KEY" in settings.missing_runtime_settings()


def test_production_missing_secrets_fail_fast() -> None:
    with pytest.raises(ValidationError):
        VoiceAgentSettings(VOICE_AGENT_ENV="production")


def test_production_replace_me_placeholder_rejected() -> None:
    """CODEX_AUDIT_PHASE_6.md YÜKSEK-3: `.env.production.example`'daki
    `REPLACE_ME` unutulup production'a taşınırsa fail-fast tetiklenmeli."""
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        VoiceAgentSettings(
            VOICE_AGENT_ENV="production",
            INTERNAL_SERVICE_TOKEN=SecretStr("a-genuinely-long-strong-token-value"),
            LIVEKIT_URL="wss://example.invalid",
            LIVEKIT_API_KEY=SecretStr("a-genuinely-long-strong-key-value"),
            LIVEKIT_API_SECRET=SecretStr("a-genuinely-long-strong-secret-value"),
            LIVEKIT_SIP_OUTBOUND_TRUNK_ID="trunk-id",
            OPENAI_API_KEY=SecretStr("REPLACE_ME"),
        )


def test_production_short_secret_rejected() -> None:
    with pytest.raises(ValidationError, match="INTERNAL_SERVICE_TOKEN"):
        VoiceAgentSettings(
            VOICE_AGENT_ENV="production",
            INTERNAL_SERVICE_TOKEN=SecretStr("short"),
            LIVEKIT_URL="wss://example.invalid",
            LIVEKIT_API_KEY=SecretStr("a-genuinely-long-strong-key-value"),
            LIVEKIT_API_SECRET=SecretStr("a-genuinely-long-strong-secret-value"),
            LIVEKIT_SIP_OUTBOUND_TRUNK_ID="trunk-id",
            OPENAI_API_KEY=SecretStr("a-genuinely-long-strong-api-key-value"),
        )


def test_runtime_ready_requires_missing_credentials() -> None:
    settings = VoiceAgentSettings(VOICE_AGENT_ENV="development")

    with pytest.raises(ConfigurationError):
        settings.require_runtime_ready()


def test_secret_repr_does_not_expose_value() -> None:
    settings = VoiceAgentSettings(INTERNAL_SERVICE_TOKEN=SecretStr("super-secret-token"))

    assert "super-secret-token" not in repr(settings)


def test_invalid_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceAgentSettings(HTTP_TIMEOUT_SECONDS=0)


def test_invalid_livekit_url_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceAgentSettings(LIVEKIT_URL="http://localhost:7880")


def _production_kwargs(**overrides: SecretStr | str) -> dict[str, SecretStr | str]:
    fields: dict[str, SecretStr | str] = {
        "VOICE_AGENT_ENV": "production",
        "INTERNAL_SERVICE_TOKEN": SecretStr("a-genuinely-long-strong-token-value"),
        "LIVEKIT_URL": "wss://example.invalid",
        "LIVEKIT_API_KEY": SecretStr("a-genuinely-long-strong-key-value"),
        "LIVEKIT_API_SECRET": SecretStr("a-genuinely-long-strong-secret-value"),
        "LIVEKIT_SIP_OUTBOUND_TRUNK_ID": "trunk-id",
        "OPENAI_API_KEY": SecretStr("a-genuinely-long-strong-api-key-value"),
    }
    fields.update(overrides)
    return fields


def test_exact_dummy_marker_rejected_in_production() -> None:
    """CODEX_FINAL_AUDIT_PHASE_6.md ORTA-2: yalnız GERÇEKTEN template olarak
    kullanılan tam `dummy` değeri reddedilmeli — substring DEĞİL."""
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        VoiceAgentSettings.model_validate(_production_kwargs(OPENAI_API_KEY=SecretStr("dummy")))


def test_strong_secret_containing_example_substring_is_accepted_in_production() -> None:
    """Önceden substring eşleşmesi nedeniyle içinde yalnızca "example" GEÇEN
    güçlü bir secret yanlışlıkla reddediliyordu (backend'le aynı regresyon)."""
    settings = VoiceAgentSettings.model_validate(
        _production_kwargs(OPENAI_API_KEY=SecretStr("prod-example-9f8e7d6c5b4a3210fedcba9876543210"))
    )
    assert settings.missing_runtime_settings() == []


def test_strong_secret_containing_dummy_substring_is_accepted_in_production() -> None:
    settings = VoiceAgentSettings.model_validate(
        _production_kwargs(OPENAI_API_KEY=SecretStr("mydummyvalue-a1b2c3d4e5f6g7h8i9j0"))
    )
    assert settings.missing_runtime_settings() == []


def test_pre_wrapped_whitespace_only_secretstr_treated_as_missing() -> None:
    """CODEX_SIGNOFF_PHASE_6.md §15: `SecretStr(" "*20)` gibi ÖNCEDEN
    SARILMIŞ bir değer `str_strip_whitespace=True`'nin parse-aşaması
    normalizasyonundan geçmeyebilir — `missing_runtime_settings()`'in
    kendi açık `.strip()`'i bunu yine de yakalamalı (production model
    validator'ı zaten construction sırasında fail-fast tetikler)."""
    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        VoiceAgentSettings.model_validate(_production_kwargs(OPENAI_API_KEY=SecretStr(" " * 20)))
