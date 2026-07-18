"""integration_settings erişimi. SECRET SAKLANMAZ — yalnız secret-olmayan
ayarlar (fiyat, kur, varsayılan model...) ve 'yapılandırıldı mı' bayrakları."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.system import IntegrationSetting

# Panelden düzenlenebilir güvenli anahtarlar (allowlist)
EDITABLE_KEYS: frozenset[tuple[str, str]] = frozenset(
    {
        ("netgsm", "price_per_minute_try"),
        ("billing", "usd_try_rate"),
        ("calls", "default_model"),
        ("calls", "default_voice"),
        ("calls", "daily_limit_override"),
        ("calls", "transcript_retention_days"),
    }
)


def get_setting(db: Session, provider: str, key: str) -> str | None:
    row = db.scalars(
        select(IntegrationSetting).where(
            IntegrationSetting.provider == provider, IntegrationSetting.setting_key == key
        )
    ).first()
    return row.safe_value if row else None


def set_setting(db: Session, provider: str, key: str, value: str | None) -> IntegrationSetting:
    if (provider, key) not in EDITABLE_KEYS:
        raise ValueError(f"Bu ayar panelden düzenlenemez: {provider}.{key}")
    row = db.scalars(
        select(IntegrationSetting).where(
            IntegrationSetting.provider == provider, IntegrationSetting.setting_key == key
        )
    ).first()
    if row is None:
        row = IntegrationSetting(provider=provider, setting_key=key)
        db.add(row)
    row.safe_value = value
    row.is_configured = value is not None and value != ""
    row.updated_at = datetime.now(UTC)
    db.flush()
    return row


def get_decimal_setting(db: Session, provider: str, key: str, default: Decimal) -> Decimal:
    raw = get_setting(db, provider, key)
    if raw is None:
        return default
    try:
        return Decimal(raw)
    except InvalidOperation:
        return default


def get_usd_try_rate(db: Session) -> tuple[Decimal | None, datetime | None]:
    row = db.scalars(
        select(IntegrationSetting).where(
            IntegrationSetting.provider == "billing",
            IntegrationSetting.setting_key == "usd_try_rate",
        )
    ).first()
    if row is None or not row.safe_value:
        return None, None
    try:
        return Decimal(row.safe_value), row.updated_at
    except InvalidOperation:
        return None, row.updated_at


def integration_status(db: Session) -> list[dict[str, object]]:
    """Entegrasyonların 'yapılandırıldı mı' durumu — secret değerleri OKUNMAZ,
    yalnız env'de dolu olup olmadıkları raporlanır."""
    s = get_settings()
    return [
        {
            "provider": "openai",
            "configured": bool(s.OPENAI_API_KEY),
            "detail": s.OPENAI_REALTIME_DEFAULT_MODEL,
        },
        {
            "provider": "livekit",
            "configured": bool(s.LIVEKIT_API_KEY and s.LIVEKIT_API_SECRET),
            "detail": s.LIVEKIT_URL,
        },
        {
            "provider": "netgsm",
            "configured": bool(s.NETGSM_SIP_USERNAME and s.NETGSM_SIP_PASSWORD),
            "detail": f"{s.NETGSM_SIP_HOST}:{s.NETGSM_SIP_PORT} ({s.NETGSM_TRANSPORT})",
        },
        {
            "provider": "sip_trunk",
            "configured": bool(s.LIVEKIT_SIP_OUTBOUND_TRUNK_ID),
            "detail": "outbound trunk",
        },
        {
            "provider": "google_places",
            "configured": s.ENABLE_GOOGLE_PLACES and bool(s.GOOGLE_PLACES_API_KEY),
            "detail": "opsiyonel",
        },
    ]
