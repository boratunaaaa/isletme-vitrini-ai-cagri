from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.pricing import ProviderPricing
from app.services.cost_service import (
    UsageTokens,
    compute_ai_cost,
    compute_call_cost,
    get_active_pricing,
)


def _pricing(model: str = "gpt-realtime-2.1-mini", **overrides) -> ProviderPricing:
    data = {
        "provider": "openai",
        "model": model,
        "input_audio_price_per_million": Decimal("10"),
        "cached_audio_price_per_million": Decimal("1"),
        "output_audio_price_per_million": Decimal("20"),
        "input_text_price_per_million": Decimal("5"),
        "cached_text_price_per_million": Decimal("0.5"),
        "output_text_price_per_million": Decimal("15"),
        "currency": "USD",
        "effective_from": datetime.now(UTC) - timedelta(days=1),
        "is_active": True,
    }
    data.update(overrides)
    return ProviderPricing(**data)


def test_ai_cost_all_token_classes_decimal_precision() -> None:
    cost = compute_ai_cost(
        UsageTokens(
            input_audio_tokens=1000,
            cached_input_audio_tokens=1000,
            output_audio_tokens=1000,
            input_text_tokens=1000,
            cached_input_text_tokens=1000,
            output_text_tokens=1000,
        ),
        _pricing(),
    )

    assert cost == Decimal("0.051500")
    assert isinstance(cost, Decimal)


def test_zero_usage_and_missing_pricing_are_zero() -> None:
    assert compute_ai_cost(UsageTokens(), _pricing()) == Decimal("0.000000")
    assert compute_ai_cost(UsageTokens(input_audio_tokens=1000), None) == Decimal("0")


def test_get_active_pricing_uses_latest_active_effective_record(db_session, clean_db) -> None:
    old = _pricing(effective_from=datetime.now(UTC) - timedelta(days=3))
    latest = _pricing(
        effective_from=datetime.now(UTC) - timedelta(days=1),
        input_audio_price_per_million=Decimal("11"),
    )
    inactive = _pricing(
        effective_from=datetime.now(UTC),
        input_audio_price_per_million=Decimal("99"),
        is_active=False,
    )
    premium = _pricing(model="gpt-realtime-2.1", input_audio_price_per_million=Decimal("30"))
    db_session.add_all([old, latest, inactive, premium])
    db_session.commit()

    assert get_active_pricing(db_session, "openai", "gpt-realtime-2.1-mini") == latest
    assert get_active_pricing(db_session, "openai", "gpt-realtime-2.1") == premium
    assert get_active_pricing(db_session, "openai", "missing") is None


def test_call_cost_total_and_try_conversion() -> None:
    cost = compute_call_cost(
        usage=UsageTokens(input_audio_tokens=1000),
        pricing=_pricing(),
        duration_seconds=61,
        netgsm_price_per_minute_try=Decimal("2.50"),
        usd_try_rate=Decimal("40"),
    )

    assert cost.ai_cost_usd == Decimal("0.010000")
    assert cost.telephony_cost_try == Decimal("5.000000")
    assert cost.telephony_cost_usd == Decimal("0.125000")
    assert cost.total_usd == Decimal("0.135000")
