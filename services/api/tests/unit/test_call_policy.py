from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.config import get_settings
from app.models.call import Call
from app.models.campaign import Campaign
from app.models.enums import CallStatus
from app.models.lead import Lead
from app.services.call_policy import (
    CallPolicyError,
    check_global_gates,
    check_limits,
    concurrent_call_count,
    daily_call_count,
    is_within_call_hours,
)


def _lead(db_session) -> Lead:
    lead = Lead(business_name="Policy Lead")
    db_session.add(lead)
    db_session.flush()
    return lead


def _campaign(db_session) -> Campaign:
    campaign = Campaign(name="Policy Campaign")
    db_session.add(campaign)
    db_session.flush()
    return campaign


def test_live_call_gate_and_development_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_CALLS_ENABLED", "false")
    get_settings.cache_clear()
    with pytest.raises(CallPolicyError) as disabled:
        check_global_gates("+905321234567")
    assert disabled.value.code == "live_calls_disabled"

    monkeypatch.setenv("LIVE_CALLS_ENABLED", "true")
    monkeypatch.setenv("TEST_PHONE_ALLOWLIST", "+905321234567")
    get_settings.cache_clear()
    check_global_gates("+905321234567")
    with pytest.raises(CallPolicyError) as not_allowed:
        check_global_gates("+905551112233")
    assert not_allowed.value.code == "not_in_allowlist"


def test_call_hours_istanbul_boundaries() -> None:
    tz = ZoneInfo("Europe/Istanbul")
    assert not is_within_call_hours(10, 17, datetime(2026, 7, 17, 9, 59, tzinfo=tz))
    assert is_within_call_hours(10, 17, datetime(2026, 7, 17, 10, 0, tzinfo=tz))
    assert is_within_call_hours(10, 17, datetime(2026, 7, 17, 16, 59, tzinfo=tz))
    assert not is_within_call_hours(10, 17, datetime(2026, 7, 17, 17, 0, tzinfo=tz))
    assert not is_within_call_hours(22, 6, datetime(2026, 7, 17, 23, 0, tzinfo=tz))
    assert not is_within_call_hours(10, 17, datetime(2026, 7, 19, 12, 0, tzinfo=tz))


def test_daily_limit_counts_today_non_cancelled_only(db_session, clean_db) -> None:
    campaign = _campaign(db_session)
    lead_1 = _lead(db_session)
    lead_2 = _lead(db_session)
    lead_3 = _lead(db_session)
    yesterday = datetime.now(UTC) - timedelta(days=1)
    db_session.add_all(
        [
            Call(lead_id=lead_1.id, campaign_id=campaign.id, status=CallStatus.QUEUED.value),
            Call(lead_id=lead_2.id, campaign_id=campaign.id, status=CallStatus.CANCELLED.value),
            Call(
                lead_id=lead_3.id,
                campaign_id=campaign.id,
                status=CallStatus.COMPLETED.value,
                created_at=yesterday,
            ),
        ]
    )
    db_session.commit()

    assert daily_call_count(db_session, campaign.id) == 1


def test_concurrent_limit_ignores_terminal_calls(db_session, clean_db) -> None:
    campaign = _campaign(db_session)
    lead_1 = _lead(db_session)
    lead_2 = _lead(db_session)
    db_session.add_all(
        [
            Call(lead_id=lead_1.id, campaign_id=campaign.id, status=CallStatus.RINGING.value),
            Call(lead_id=lead_2.id, campaign_id=campaign.id, status=CallStatus.COMPLETED.value),
        ]
    )
    db_session.commit()

    assert concurrent_call_count(db_session, campaign.id) == 1


def test_check_limits_enforces_global_and_campaign_limits(
    db_session, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_DAILY_CALLS", "1")
    monkeypatch.setenv("MAX_CONCURRENT_CALLS", "5")
    get_settings.cache_clear()
    lead_1 = _lead(db_session)
    db_session.add(Call(lead_id=lead_1.id, status=CallStatus.COMPLETED.value))
    db_session.commit()

    with pytest.raises(CallPolicyError) as limit_error:
        check_limits(db_session, None)
    assert limit_error.value.code == "daily_limit"

    monkeypatch.setenv("MAX_DAILY_CALLS", "100")
    monkeypatch.setenv("CAMPAIGNS_ENABLED", "true")
    get_settings.cache_clear()
    campaign = Campaign(name="Limit", daily_limit=1, concurrent_call_limit=1)
    db_session.add(campaign)
    db_session.flush()
    lead_2 = _lead(db_session)
    db_session.add(
        Call(lead_id=lead_2.id, campaign_id=campaign.id, status=CallStatus.RINGING.value)
    )
    db_session.commit()

    with pytest.raises(CallPolicyError) as campaign_error:
        check_limits(db_session, campaign)
    assert campaign_error.value.code in {"campaign_daily_limit", "campaign_concurrent_limit"}
