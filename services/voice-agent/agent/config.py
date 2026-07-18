from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.errors import ConfigurationError


class VoiceAgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        case_sensitive=True,
        str_strip_whitespace=True,
    )

    VOICE_AGENT_ENV: Literal["development", "test", "staging", "production"] = "development"
    VOICE_AGENT_NAME: str = Field(default="isletme-vitrini-voice-agent", min_length=2)

    INTERNAL_API_BASE_URL: HttpUrl = "http://api:8000"  # type: ignore[assignment]
    INTERNAL_SERVICE_TOKEN: SecretStr = SecretStr("")
    INTERNAL_SERVICE_NAME: str = Field(default="voice-agent", min_length=2)

    LIVEKIT_URL: str = ""
    LIVEKIT_API_KEY: SecretStr = SecretStr("")
    LIVEKIT_API_SECRET: SecretStr = SecretStr("")
    LIVEKIT_AGENT_NAME: str = Field(default="isletme-vitrini-outbound-agent", min_length=2)
    LIVEKIT_SIP_OUTBOUND_TRUNK_ID: str = ""

    OPENAI_API_KEY: SecretStr = SecretStr("")
    OPENAI_REALTIME_DEFAULT_MODEL: str = "gpt-realtime-2.1-mini"
    OPENAI_REALTIME_PREMIUM_MODEL: str = "gpt-realtime-2.1"
    OPENAI_REALTIME_DEFAULT_VOICE: str = "marin"

    HTTP_TIMEOUT_SECONDS: float = Field(default=10, gt=0, le=60)
    HTTP_MAX_RETRIES: int = Field(default=3, ge=0, le=10)
    # 429 `Retry-After` başlığı bu değerden büyükse kırpılır (testlerde küçük
    # bir değere düşürülüp gerçek üst-sınır davranışı saniyeler içinde
    # doğrulanabilir; production'da makul bir varsayılan).
    HTTP_MAX_RETRY_AFTER_SECONDS: float = Field(default=30, gt=0, le=120)
    EVENT_QUEUE_MAX_SIZE: int = Field(default=500, ge=10, le=10_000)
    TRANSCRIPT_QUEUE_MAX_SIZE: int = Field(default=250, ge=10, le=10_000)
    USAGE_FLUSH_INTERVAL_SECONDS: float = Field(default=5, gt=0, le=120)
    GRACEFUL_SHUTDOWN_SECONDS: float = Field(default=15, gt=0, le=120)
    SIP_PARTICIPANT_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=180)
    REALTIME_STARTUP_TIMEOUT_SECONDS: float = Field(default=30, gt=0, le=180)
    SILENCE_WATCHDOG_SECONDS: float = Field(default=45, gt=0, le=600)
    # `end_call_safely` tool'u çağrıldıktan sonra modelin kapanış cümlesini
    # bitirmesi için beklenecek üst sınır (agent_state_changed ile izlenir).
    END_CALL_GRACE_SECONDS: float = Field(default=8, gt=0, le=60)
    LOG_LEVEL: str = "INFO"

    @field_validator("LIVEKIT_URL")
    @classmethod
    def _livekit_url(cls, value: str) -> str:
        if not value:
            return value
        if not (value.startswith("ws://") or value.startswith("wss://")):
            raise ValueError("LIVEKIT_URL must start with ws:// or wss://")
        return value

    @field_validator("OPENAI_REALTIME_DEFAULT_MODEL", "OPENAI_REALTIME_PREMIUM_MODEL")
    @classmethod
    def _allowed_model(cls, value: str) -> str:
        if value not in {"gpt-realtime-2.1-mini", "gpt-realtime-2.1"}:
            raise ValueError("unsupported realtime model")
        return value

    @field_validator("OPENAI_REALTIME_DEFAULT_VOICE")
    @classmethod
    def _allowed_voice(cls, value: str) -> str:
        if value not in {
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
        }:
            raise ValueError("unsupported realtime voice")
        return value

    @model_validator(mode="after")
    def _production_requires_secrets(self) -> VoiceAgentSettings:
        if self.VOICE_AGENT_ENV == "production":
            missing = self.missing_runtime_settings()
            if missing:
                raise ValueError("missing production settings: " + ", ".join(missing))
        return self

    def missing_runtime_settings(self) -> list[str]:
        missing: list[str] = []
        for name in (
            "INTERNAL_SERVICE_TOKEN",
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "LIVEKIT_SIP_OUTBOUND_TRUNK_ID",
            "OPENAI_API_KEY",
        ):
            value = getattr(self, name)
            raw = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
            if not raw:
                missing.append(name)
        return missing

    def require_runtime_ready(self) -> None:
        missing = self.missing_runtime_settings()
        if missing:
            raise ConfigurationError("missing runtime settings: " + ", ".join(missing))

    @property
    def internal_api_prefix(self) -> str:
        return str(self.INTERNAL_API_BASE_URL).rstrip("/") + "/api/internal/v1"

    @property
    def internal_token(self) -> str:
        return self.INTERNAL_SERVICE_TOKEN.get_secret_value()

    @property
    def openai_api_key(self) -> str:
        return self.OPENAI_API_KEY.get_secret_value()


@lru_cache
def get_settings() -> VoiceAgentSettings:
    try:
        return VoiceAgentSettings()
    except ValidationError as exc:
        raise ConfigurationError(str(exc)) from exc
