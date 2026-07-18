"""Agent talimatı derleyici.

Sistem promptu tek parça hard-code DEĞİLDİR: aktif AgentPromptVersion +
bilgi bankası (knowledge_base_entries) + kampanya hedefi + işletme bağlamı
çalışma anında birleştirilir. Kullanılan prompt versiyonu call kaydına yazılır.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
from app.models.lead import Lead


class PromptError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuiltPrompt:
    prompt_version_id: str
    prompt_version_name: str
    instructions: str
    opening_hint: str


def get_active_prompt_version(db: Session) -> AgentPromptVersion:
    version = db.scalars(
        select(AgentPromptVersion).where(AgentPromptVersion.is_active.is_(True)).limit(1)
    ).first()
    if version is None:
        raise PromptError(
            "Aktif agent prompt versiyonu yok. Seed çalıştırın veya panelden aktifleştirin."
        )
    return version


def _kb_sections(db: Session) -> str:
    entries = db.scalars(
        select(KnowledgeBaseEntry)
        .where(KnowledgeBaseEntry.is_active.is_(True))
        .order_by(KnowledgeBaseEntry.category, KnowledgeBaseEntry.title)
    ).all()
    if not entries:
        return "(Bilgi bankası boş — emin olmadığın hiçbir bilgiyi uydurma.)"
    blocks: list[str] = []
    current_category = None
    for entry in entries:
        if entry.category != current_category:
            blocks.append(f"\n### {entry.category}")
            current_category = entry.category
        blocks.append(f"- **{entry.title}**: {entry.content}")
    return "\n".join(blocks)


def _lead_context(lead: Lead) -> str:
    parts = [f"İşletme adı: {lead.business_name}"]
    if lead.sector:
        parts.append(f"Sektör: {lead.sector}")
    if lead.district or lead.city:
        parts.append(f"Bölge: {', '.join(x for x in [lead.district, lead.city] if x)}")
    if lead.rating is not None:
        parts.append(f"Google puanı: {lead.rating} ({lead.review_count or 0} yorum)")
    if lead.website:
        parts.append("Web sitesi durumu: Mevcut bir web sitesi var — eleştirme, ihtiyacı sor.")
    else:
        parts.append("Web sitesi durumu: Bilinen bir web sitesi yok.")
    return "\n".join(parts)


def build_agent_instructions(
    db: Session,
    *,
    lead: Lead,
    campaign: Campaign | None,
    prompt_version: AgentPromptVersion | None = None,
) -> BuiltPrompt:
    version = prompt_version or get_active_prompt_version(db)
    campaign_goal = (
        f"\n## Kampanya hedefi\n{campaign.description}" if campaign and campaign.description else ""
    )
    instructions = "\n\n".join(
        section
        for section in (
            version.system_prompt,
            f"## Görüşme hedefi\n{version.objective}",
            f"## İtiraz karşılama kuralları\n{version.objection_rules}",
            f"## Bilgi bankası (tek doğru kaynak — bunun dışına çıkma)\n{_kb_sections(db)}",
            f"## Bu görüşmenin işletme bağlamı\n{_lead_context(lead)}",
            campaign_goal.strip(),
            "## Açılış\n"
            f"Açılış yaklaşımın: {version.opening_script}\n"
            "Kelimesi kelimesine okuma; doğal varyasyon serbest, anlam sabit.",
        )
        if section
    )
    return BuiltPrompt(
        prompt_version_id=str(version.id),
        prompt_version_name=version.name,
        instructions=instructions,
        opening_hint=version.opening_script,
    )
