"""Arama politikaları: güvenlik kapıları, saat/limit kontrolleri, retry hesabı.

Tüm kontroller SERVER tarafındadır; frontend yalnız kullanıcı deneyimi için
aynı kuralları gösterir.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import ACTIVE_CALL_STATUSES, CallOutcome, CallStatus


class CallPolicyError(Exception):
    """Politika ihlali; code makine-okunur, message kullanıcıya gösterilebilir."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def now_istanbul() -> datetime:
    return datetime.now(ZoneInfo(get_settings().APP_TIMEZONE))


def is_within_call_hours(start_hour: int, end_hour: int, at: datetime | None = None) -> bool:
    current = at or now_istanbul()
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo(get_settings().APP_TIMEZONE))
    else:
        current = current.astimezone(ZoneInfo(get_settings().APP_TIMEZONE))
    if current.weekday() == 6:  # Pazar günü arama yapılmaz
        return False
    return start_hour <= current.hour < end_hour


def _today_bounds_utc() -> tuple[datetime, datetime]:
    tz = ZoneInfo(get_settings().APP_TIMEZONE)
    local_now = datetime.now(tz)
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start.astimezone(UTC), (day_start + timedelta(days=1)).astimezone(UTC)


def daily_call_count(db: Session, campaign_id: uuid.UUID | None = None) -> int:
    start, end = _today_bounds_utc()
    query = select(func.count(Call.id)).where(
        Call.created_at >= start,
        Call.created_at < end,
        Call.status != CallStatus.CANCELLED.value,
    )
    if campaign_id is not None:
        query = query.where(Call.campaign_id == campaign_id)
    return int(db.scalar(query) or 0)


def concurrent_call_count(db: Session, campaign_id: uuid.UUID | None = None) -> int:
    query = select(func.count(Call.id)).where(
        Call.status.in_([s.value for s in ACTIVE_CALL_STATUSES])
    )
    if campaign_id is not None:
        query = query.where(Call.campaign_id == campaign_id)
    return int(db.scalar(query) or 0)


def check_global_gates(phone_e164: str) -> None:
    """LIVE_CALLS_ENABLED + development allowlist kontrolü."""
    s = get_settings()
    if not s.LIVE_CALLS_ENABLED:
        raise CallPolicyError(
            "live_calls_disabled",
            "Canlı aramalar kapalı (LIVE_CALLS_ENABLED=false). Arama başlatılmadı.",
        )
    if not s.is_production:
        allowlist = s.test_phone_allowlist
        if phone_e164 not in allowlist:
            raise CallPolicyError(
                "not_in_allowlist",
                "Development ortamında yalnız TEST_PHONE_ALLOWLIST içindeki numaralar aranabilir.",
            )


def check_limits(db: Session, campaign: Campaign | None) -> None:
    s = get_settings()
    if daily_call_count(db) >= s.MAX_DAILY_CALLS:
        raise CallPolicyError("daily_limit", "Günlük genel arama limiti doldu.")
    if concurrent_call_count(db) >= s.MAX_CONCURRENT_CALLS:
        raise CallPolicyError("concurrent_limit", "Eşzamanlı arama limiti dolu.")
    if campaign is not None:
        if not s.CAMPAIGNS_ENABLED:
            raise CallPolicyError(
                "campaigns_disabled", "Kampanyalar kapalı (CAMPAIGNS_ENABLED=false)."
            )
        if daily_call_count(db, campaign.id) >= campaign.daily_limit:
            raise CallPolicyError("campaign_daily_limit", "Kampanya günlük limiti doldu.")
        if concurrent_call_count(db, campaign.id) >= campaign.concurrent_call_limit:
            raise CallPolicyError("campaign_concurrent_limit", "Kampanya eşzamanlı limiti dolu.")


def check_call_hours(campaign: Campaign | None) -> None:
    s = get_settings()
    start = campaign.call_start_hour if campaign else s.DEFAULT_CALL_START_HOUR
    end = campaign.call_end_hour if campaign else s.DEFAULT_CALL_END_HOUR
    if not is_within_call_hours(start, end):
        raise CallPolicyError(
            "outside_call_hours",
            f"Arama saatleri dışında ({start:02d}:00–{end:02d}:00 {s.APP_TIMEZONE}).",
        )


# ─── Retry hesaplama ─────────────────────────────────────────────────────────

# Telephony sonucuna göre tekrar deneme çarpanı (dakika cinsinden taban gecikmeye göre)
_RETRY_MULTIPLIER: dict[str, float] = {
    CallStatus.BUSY.value: 0.5,  # meşgulse daha erken dene
    CallStatus.NO_ANSWER.value: 1.0,
    CallStatus.VOICEMAIL.value: 2.0,  # telesekreterse daha geç dene
    CallStatus.FAILED.value: 1.0,
    CallStatus.REJECTED.value: 2.0,
}

# Bu sonuçlarda ASLA tekrar aranmaz
NO_RETRY_OUTCOMES: frozenset[str] = frozenset(
    {
        CallOutcome.DO_NOT_CALL.value,
        CallOutcome.WRONG_NUMBER.value,
        CallOutcome.BUSINESS_CLOSED.value,
        CallOutcome.NOT_INTERESTED.value,
        CallOutcome.INTERESTED.value,
        CallOutcome.DEMO_REQUESTED.value,
        CallOutcome.TRANSFERRED_TO_HUMAN.value,
    }
)


def compute_next_retry(
    *,
    call_status: str,
    outcome: str | None,
    attempt_count: int,
    max_retry_count: int,
    retry_delay_minutes: int,
    callback_at: datetime | None = None,
) -> datetime | None:
    """Bir sonraki deneme zamanı; None ise tekrar denenmez.

    - callback istenmişse o zaman esas alınır (retry sayılmaz).
    - Exponential backoff: taban gecikme × durum çarpanı × 2^(deneme-1).
    - Aynı gün kontrolsüz tekrar aramayı önlemek için minimum 60 dk.
    """
    if callback_at is not None:
        return callback_at
    if outcome in NO_RETRY_OUTCOMES:
        return None
    if attempt_count >= max_retry_count + 1:  # ilk deneme + retry hakları
        return None
    if call_status == CallStatus.COMPLETED.value and outcome is None:
        return None
    multiplier = _RETRY_MULTIPLIER.get(call_status)
    if multiplier is None:
        return None
    delay_minutes = max(60.0, retry_delay_minutes * multiplier * (2 ** max(attempt_count - 1, 0)))
    return datetime.now(UTC) + timedelta(minutes=delay_minutes)
