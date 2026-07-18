"""Uygulama yapılandırması.

Tüm secret'lar environment üzerinden gelir. Production'da eksik kritik secret
uygulamayı başlatmaz (fail-fast). Development'ta eksik secret'lar güvensiz
oldukları açıkça loglanan deterministik DEV değerleriyle doldurulur ki lokal
geliştirme sürtünmesiz olsun.
"""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEV_SECRET_FIELDS = (
    "JWT_SECRET",
    "COOKIE_SECRET",
    "PII_ENCRYPTION_KEY",
    "PHONE_HASH_PEPPER",
    "INTERNAL_SERVICE_TOKEN",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    APP_ENV: str = "development"
    APP_NAME: str = "isletme-vitrini-ai-cagri"
    APP_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"
    APP_TIMEZONE: str = "Europe/Istanbul"
    CORS_ORIGINS: str = "http://localhost:3000"
    TRUSTED_HOSTS: str = "localhost,127.0.0.1"

    DATABASE_URL: str = "postgresql+psycopg://ivac:ivac@localhost:5432/ivac"
    DATABASE_URL_TEST: str = "postgresql+psycopg://ivac:ivac@localhost:5432/ivac_test"
    REDIS_URL: str = "redis://localhost:6379/0"

    JWT_SECRET: str = ""
    COOKIE_SECRET: str = ""
    PII_ENCRYPTION_KEY: str = ""
    PHONE_HASH_PEPPER: str = ""
    INTERNAL_SERVICE_TOKEN: str = ""
    INTERNAL_SERVICE_TOKEN_PREVIOUS: str = ""
    INTERNAL_SERVICE_NAME: str = "voice-agent"
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""
    LIVEKIT_SIP_OUTBOUND_TRUNK_ID: str = ""
    LIVEKIT_AGENT_NAME: str = "ivac-outbound-agent"

    NETGSM_SIP_HOST: str = "sip.netgsm.com.tr"
    NETGSM_SIP_PORT: int = 5060
    NETGSM_SIP_USERNAME: str = ""
    NETGSM_SIP_PASSWORD: str = ""
    NETGSM_OUTBOUND_NUMBER: str = ""
    NETGSM_TRANSPORT: str = "udp"
    NETGSM_CODEC_PREFERENCES: str = "PCMA,PCMU"

    OPENAI_API_KEY: str = ""
    OPENAI_REALTIME_DEFAULT_MODEL: str = "gpt-realtime-2.1-mini"
    OPENAI_REALTIME_PREMIUM_MODEL: str = "gpt-realtime-2.1"
    OPENAI_REALTIME_DEFAULT_VOICE: str = "marin"
    OPENAI_REALTIME_REASONING_EFFORT: str = "low"

    DEFAULT_CONVERSATION_ENGINE: str = "openai_realtime"
    ENABLE_OPENAI_REALTIME: bool = True
    ENABLE_LOCAL_PIPELINE: bool = False

    GOOGLE_PLACES_API_KEY: str = ""
    ENABLE_GOOGLE_PLACES: bool = False

    LIVE_CALLS_ENABLED: bool = False
    CAMPAIGNS_ENABLED: bool = False
    TEST_PHONE_ALLOWLIST: str = ""
    MAX_CONCURRENT_CALLS: int = 1
    MAX_DAILY_CALLS: int = 10

    DEFAULT_CALL_START_HOUR: int = 10
    DEFAULT_CALL_END_HOUR: int = 17
    MAX_CALL_DURATION_SECONDS: int = 300
    DEFAULT_MAX_RETRY_COUNT: int = 2
    DEFAULT_RETRY_DELAY_MINUTES: int = 120

    CALL_RECORDING_ENABLED: bool = False
    TRANSCRIPT_STORAGE_ENABLED: bool = True
    TRANSCRIPT_RETENTION_DAYS: int = 30
    AUDIO_RETENTION_DAYS: int = 0

    HUMAN_TRANSFER_ENABLED: bool = False
    HUMAN_TRANSFER_NUMBER: str = ""

    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""

    SESSION_IDLE_SECONDS: int = 12 * 3600
    SESSION_ABSOLUTE_SECONDS: int = 7 * 24 * 3600

    @field_validator("DEFAULT_CALL_START_HOUR", "DEFAULT_CALL_END_HOUR")
    @classmethod
    def _valid_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("Saat 0-23 aralığında olmalı")
        return v

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def test_phone_allowlist(self) -> frozenset[str]:
        return frozenset(p.strip() for p in self.TEST_PHONE_ALLOWLIST.split(",") if p.strip())

    @property
    def cors_origins(self) -> list[str]:
        values = [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return values or [self.APP_URL]

    @property
    def trusted_hosts(self) -> list[str]:
        values = [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]
        return values or ["localhost", "127.0.0.1"]

    def validate_runtime(self) -> None:
        """Production'da kritik secret eksikse uygulamayı başlatma (fail-fast)."""
        missing = [f for f in _DEV_SECRET_FIELDS if not getattr(self, f)]
        if self.is_production:
            if missing:
                raise RuntimeError(
                    f"Production ortamında eksik zorunlu secret'lar: {', '.join(missing)}"
                )
            for field in ("INTERNAL_SERVICE_TOKEN", "INTERNAL_SERVICE_TOKEN_PREVIOUS"):
                value = getattr(self, field)
                if value and (len(value) < 32 or value.startswith("dev-insecure-")):
                    raise RuntimeError(f"Production {field} zayıf olamaz")
            if "postgresql" not in self.DATABASE_URL:
                raise RuntimeError("Production DATABASE_URL PostgreSQL olmalı")
            if self.APP_URL.startswith("http://") and "localhost" not in self.APP_URL:
                raise RuntimeError("Production APP_URL HTTPS olmalı")
        else:
            for field in missing:
                dev_value = (
                    "dev-insecure-"
                    + hashlib.sha256(f"{self.APP_NAME}:{field}".encode()).hexdigest()[:32]
                )
                setattr(self, field, dev_value)
            if missing:
                logger.warning(
                    "DEV ORTAMI: eksik secret'lar güvensiz DEV değerleriyle dolduruldu: %s",
                    ", ".join(missing),
                )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
