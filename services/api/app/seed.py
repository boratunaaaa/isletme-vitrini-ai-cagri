from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select, update

from app.config import get_settings
from app.db.session import session_scope
from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
from app.models.pricing import ProviderPricing
from app.models.system import IntegrationSetting


@dataclass(frozen=True)
class PricingSeed:
    provider: str
    model: str
    input_audio: Decimal
    cached_audio: Decimal
    output_audio: Decimal
    input_text: Decimal = Decimal("0")
    cached_text: Decimal = Decimal("0")
    output_text: Decimal = Decimal("0")


PACKAGE_KB = [
    (
        "paketler",
        "Ekonomik Vitrin",
        "Ekonomik Vitrin paketi 1.990 TL başlangıç fiyatıyla tek sayfalık sade tanıtım sunar.",
    ),
    (
        "paketler",
        "İşletme Sitesi",
        "İşletme Sitesi paketi 3.990 TL başlangıç fiyatıyla daha kapsamlı işletme web "
        "varlığı sunar.",
    ),
    (
        "paketler",
        "Profesyonel Site",
        "Profesyonel Site paketi 7.490 TL başlangıç fiyatıyla daha gelişmiş içerik ve yapı sunar.",
    ),
]

BASE_KB = [
    (
        "hizmet",
        "İşletme Vitrini nedir?",
        "İşletme Vitrini, web sitesi olmayan veya dijital görünürlüğünü güçlendirmek isteyen "
        "yerel işletmelere hızlı hazırlanabilen tanıtım sayfaları ve web sitesi paketleri sunar.",
    ),
    (
        "gorusme",
        "Arama hedefi",
        "Görüşmenin hedefi işletmenin ihtiyacını anlamak, kısa ve doğal şekilde çözümü anlatmak "
        "ve uygun ise demo veya geri arama talebi oluşturmaktır.",
    ),
]

DEFAULT_PROMPT = {
    "name": "default-v1",
    "system_prompt": (
        "Sen İşletme Vitrini için Türkçe konuşan, sakin ve dürüst bir satış asistanısın. "
        "Bilgi bankasında olmayan fiyat, garanti veya teknik iddia uydurma."
    ),
    "opening_script": (
        "Merhaba, İşletme Vitrini'nden arıyorum. Kısa bir uygunluk sorusu sormak istedim."
    ),
    "objective": (
        "İşletmenin web görünürlüğü ihtiyacını anlamak, ilgisi varsa ücretsiz demo veya geri arama "
        "talebi kaydetmek."
    ),
    "objection_rules": (
        "Meşgulse ısrar etme ve geri arama zamanı iste. İlgilenmiyorsa kibarca kapat. "
        "Aranmak istemediğini söylerse suppression kaydı oluşturulmasını sağla."
    ),
}


def _pricing_rows() -> list[PricingSeed]:
    settings = get_settings()
    return [
        PricingSeed(
            "openai",
            settings.OPENAI_REALTIME_DEFAULT_MODEL,
            input_audio=Decimal("10"),
            cached_audio=Decimal("0"),
            output_audio=Decimal("20"),
        ),
        PricingSeed(
            "openai",
            settings.OPENAI_REALTIME_PREMIUM_MODEL,
            input_audio=Decimal("32"),
            cached_audio=Decimal("0"),
            output_audio=Decimal("64"),
        ),
    ]


def seed_all() -> dict[str, int]:
    counts = {"pricing": 0, "settings": 0, "kb": 0, "prompts": 0}
    with session_scope() as db:
        for item in _pricing_rows():
            existing = db.scalars(
                select(ProviderPricing).where(
                    ProviderPricing.provider == item.provider,
                    ProviderPricing.model == item.model,
                    ProviderPricing.is_active.is_(True),
                )
            ).first()
            if existing is None:
                db.add(
                    ProviderPricing(
                        provider=item.provider,
                        model=item.model,
                        input_audio_price_per_million=item.input_audio,
                        cached_audio_price_per_million=item.cached_audio,
                        output_audio_price_per_million=item.output_audio,
                        input_text_price_per_million=item.input_text,
                        cached_text_price_per_million=item.cached_text,
                        output_text_price_per_million=item.output_text,
                    )
                )
                counts["pricing"] += 1

        default_settings = {
            ("calls", "default_model"): get_settings().OPENAI_REALTIME_DEFAULT_MODEL,
            ("calls", "default_voice"): get_settings().OPENAI_REALTIME_DEFAULT_VOICE,
            ("netgsm", "price_per_minute_try"): "0",
            ("billing", "usd_try_rate"): None,
        }
        for (provider, key), value in default_settings.items():
            setting = db.scalars(
                select(IntegrationSetting).where(
                    IntegrationSetting.provider == provider,
                    IntegrationSetting.setting_key == key,
                )
            ).first()
            if setting is None:
                db.add(
                    IntegrationSetting(
                        provider=provider,
                        setting_key=key,
                        safe_value=value,
                        is_configured=value is not None,
                    )
                )
                counts["settings"] += 1

        for category, title, content in [*PACKAGE_KB, *BASE_KB]:
            kb_entry = db.scalars(
                select(KnowledgeBaseEntry).where(
                    KnowledgeBaseEntry.category == category,
                    KnowledgeBaseEntry.title == title,
                )
            ).first()
            if kb_entry is None:
                db.add(KnowledgeBaseEntry(category=category, title=title, content=content))
                counts["kb"] += 1

        prompt = db.scalars(
            select(AgentPromptVersion).where(AgentPromptVersion.name == DEFAULT_PROMPT["name"])
        ).first()
        if prompt is None:
            db.add(AgentPromptVersion(**DEFAULT_PROMPT, is_active=True))
            counts["prompts"] += 1
        else:
            db.execute(
                update(AgentPromptVersion)
                .where(AgentPromptVersion.name != DEFAULT_PROMPT["name"])
                .values(is_active=False)
            )
            prompt.is_active = True
    return counts


def main() -> int:
    counts = seed_all()
    print(
        "seed complete: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
