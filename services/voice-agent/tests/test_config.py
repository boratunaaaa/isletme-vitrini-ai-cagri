from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.config import VoiceAgentSettings
from agent.errors import ConfigurationError


def test_development_import_allows_missing_runtime_credentials() -> None:
    settings = VoiceAgentSettings(VOICE_AGENT_ENV="development")

    assert "OPENAI_API_KEY" in settings.missing_runtime_settings()


def test_production_missing_secrets_fail_fast() -> None:
    with pytest.raises(ValidationError):
        VoiceAgentSettings(VOICE_AGENT_ENV="production")


def test_runtime_ready_requires_missing_credentials() -> None:
    settings = VoiceAgentSettings(VOICE_AGENT_ENV="development")

    with pytest.raises(ConfigurationError):
        settings.require_runtime_ready()


def test_secret_repr_does_not_expose_value() -> None:
    settings = VoiceAgentSettings(INTERNAL_SERVICE_TOKEN="super-secret-token")

    assert "super-secret-token" not in repr(settings)


def test_invalid_timeout_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceAgentSettings(HTTP_TIMEOUT_SECONDS=0)


def test_invalid_livekit_url_rejected() -> None:
    with pytest.raises(ValidationError):
        VoiceAgentSettings(LIVEKIT_URL="http://localhost:7880")
