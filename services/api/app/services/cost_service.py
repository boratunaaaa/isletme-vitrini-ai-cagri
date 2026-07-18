"""Maliyet motoru.

AI maliyeti: token kullanımı × provider_pricing (1M token başına USD).
Telefon maliyeti: dakika fiyatı (TRY, panelden) → USD (panelden girilen kur).
Tahmin ile provider verisi `usage_source` alanıyla ayrılır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pricing import ProviderPricing

MILLION = Decimal("1000000")


@dataclass(frozen=True)
class UsageTokens:
    input_audio_tokens: int = 0
    cached_input_audio_tokens: int = 0
    output_audio_tokens: int = 0
    input_text_tokens: int = 0
    cached_input_text_tokens: int = 0
    output_text_tokens: int = 0
    reasoning_tokens: int | None = None


@dataclass(frozen=True)
class CostBreakdown:
    ai_cost_usd: Decimal
    telephony_cost_usd: Decimal
    telephony_cost_try: Decimal
    total_usd: Decimal


def get_active_pricing(db: Session, provider: str, model: str) -> ProviderPricing | None:
    return db.scalars(
        select(ProviderPricing)
        .where(
            ProviderPricing.provider == provider,
            ProviderPricing.model == model,
            ProviderPricing.is_active.is_(True),
        )
        .order_by(ProviderPricing.effective_from.desc())
        .limit(1)
    ).first()


def compute_ai_cost(usage: UsageTokens, pricing: ProviderPricing | None) -> Decimal:
    if pricing is None:
        return Decimal("0")
    total = (
        Decimal(usage.input_audio_tokens) * pricing.input_audio_price_per_million
        + Decimal(usage.cached_input_audio_tokens) * pricing.cached_audio_price_per_million
        + Decimal(usage.output_audio_tokens) * pricing.output_audio_price_per_million
        + Decimal(usage.input_text_tokens) * pricing.input_text_price_per_million
        + Decimal(usage.cached_input_text_tokens) * pricing.cached_text_price_per_million
        + Decimal(usage.output_text_tokens) * pricing.output_text_price_per_million
    ) / MILLION
    return total.quantize(Decimal("0.000001"))


def compute_telephony_cost_try(
    duration_seconds: int | None, price_per_minute_try: Decimal
) -> Decimal:
    if not duration_seconds or duration_seconds <= 0:
        return Decimal("0")
    minutes = Decimal(math.ceil(duration_seconds / 60))
    return (minutes * price_per_minute_try).quantize(Decimal("0.000001"))


def try_to_usd(amount_try: Decimal, usd_try_rate: Decimal | None) -> Decimal:
    if not usd_try_rate or usd_try_rate <= 0:
        return Decimal("0")
    return (amount_try / usd_try_rate).quantize(Decimal("0.000001"))


def compute_call_cost(
    *,
    usage: UsageTokens,
    pricing: ProviderPricing | None,
    duration_seconds: int | None,
    netgsm_price_per_minute_try: Decimal,
    usd_try_rate: Decimal | None,
) -> CostBreakdown:
    ai_usd = compute_ai_cost(usage, pricing)
    tel_try = compute_telephony_cost_try(duration_seconds, netgsm_price_per_minute_try)
    tel_usd = try_to_usd(tel_try, usd_try_rate)
    return CostBreakdown(
        ai_cost_usd=ai_usd,
        telephony_cost_usd=tel_usd,
        telephony_cost_try=tel_try,
        total_usd=(ai_usd + tel_usd).quantize(Decimal("0.000001")),
    )
