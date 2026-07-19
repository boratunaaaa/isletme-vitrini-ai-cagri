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

# NOT (CODEX_AUDIT_PHASE_6.md YÜKSEK-3): `.env.production.example`'daki
# `REPLACE_ME` değerleri unutulup production'a taşınırsa önceden yalnız
# "eksik mi" kontrol ediliyordu — "dolu ama açıkça placeholder" değerler
# fail-fast'i atlatabiliyordu. Bu markerler + minimum uzunluk eşiği,
# `validate_runtime()` içinde tüm kritik secret'lar için uygulanır. Marker'lar
# kanonik (ayraçsız) biçimde tutulur; karşılaştırma öncesi hem değer hem
# marker'lardan `-`/`_`/boşluk temizlenir — böylece `changeme`, `change-me`,
# `CHANGE_ME`, `change me` gibi TÜM varyantlar tek kural ile yakalanır.
_PLACEHOLDER_MARKERS = (
    "replaceme",
    "changeme",
    "example",
    "dummy",
    "yoursecrethere",
)
_MIN_SECRET_LENGTH = 20


def _normalize_for_placeholder_check(value: str) -> str:
    """Marker karşılaştırması için ayraçsız/boşluksuz küçük harf biçimi."""
    return value.lower().replace("-", "").replace("_", "").replace(" ", "")


class Settings(BaseSettings):
    # NOT (CODEX_REAUDIT_PHASE_6.md YÜKSEK-3): `str_strip_whitespace=True`
    # voice-agent'ın `VoiceAgentSettings`'iyle TUTARLI — whitespace-only bir
    # env değeri (`"                    "`) pydantic parse aşamasında `""`e
    # normalize edilir, böylece aşağıdaki `missing`/uzunluk kontrolleri
    # BAŞTAN doğru çalışır (ayrıca `validate_runtime()` içinde de açıkça
    # `.strip()` uygulanır — defense-in-depth, bu bayrağa tek başına
    # güvenilmez).
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=True, str_strip_whitespace=True
    )

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
        """Production'da kritik secret eksikse uygulamayı başlatma (fail-fast).

        NOT (CODEX_REAUDIT_PHASE_6.md YÜKSEK-3): tüm secret değerleri
        kontrolden ÖNCE `.strip()` ile normalize edilir — yalnız whitespace
        içeren bir değer (`model_config`'teki `str_strip_whitespace=True`
        pydantic parse aşamasında bunu zaten `""`e çevirir, ama bu fonksiyon
        o bayrağa TEK BAŞINA güvenmez, kendi içinde de açıkça strip eder)
        "dolu" sayılmaz — boşsa `missing` listesine girer, üretim ortamında
        fail-fast tetiklenir. Python'ın `str.strip()`'i standart ASCII
        boşluk/tab/newline'ın yanı sıra Unicode non-breaking space
        (` `) gibi `str.isspace()` TRUE dönen karakterleri de kapsar.
        """
        normalized = {f: getattr(self, f).strip() for f in _DEV_SECRET_FIELDS}
        missing = [f for f in _DEV_SECRET_FIELDS if not normalized[f]]
        if self.is_production:
            if missing:
                raise RuntimeError(
                    f"Production ortamında eksik zorunlu secret'lar: {', '.join(missing)}"
                )
            for field in _DEV_SECRET_FIELDS:
                value = normalized[field]
                canonical = _normalize_for_placeholder_check(value)
                # NOT (CODEX_FINAL_AUDIT_PHASE_6.md ORTA-2): önceden `marker in
                # canonical` (substring) kullanılıyordu — `prefix-example-<uzun
                # rastgele değer>` gibi GÜÇLÜ bir secret, içinde yalnızca
                # "example" GEÇTİĞİ için yanlışlıkla reddediliyordu. Artık
                # normalize edilmiş değer TAM OLARAK bilinen bir placeholder
                # marker'a EŞİT olmalı — substring değil, tam eşleşme.
                if len(value) < _MIN_SECRET_LENGTH or canonical in _PLACEHOLDER_MARKERS:
                    raise RuntimeError(
                        f"Production {field} zayıf veya placeholder görünüyor "
                        f"(en az {_MIN_SECRET_LENGTH} karakter olmalı, yalnız whitespace "
                        f"OLAMAZ, '{'/'.join(_PLACEHOLDER_MARKERS)}' gibi placeholder "
                        "kelimeler içeremez)"
                    )
            for field in ("INTERNAL_SERVICE_TOKEN", "INTERNAL_SERVICE_TOKEN_PREVIOUS"):
                value = getattr(self, field).strip()
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
