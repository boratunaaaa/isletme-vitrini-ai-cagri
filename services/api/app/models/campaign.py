from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import CampaignLeadStatus, CampaignStatus, ConversationEngine


class Campaign(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "campaigns"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CampaignStatus.DRAFT.value, index=True
    )
    conversation_engine: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ConversationEngine.OPENAI_REALTIME.value
    )
    realtime_model: Mapped[str] = mapped_column(
        String(80), nullable=False, default="gpt-realtime-2.1-mini"
    )
    realtime_voice: Mapped[str] = mapped_column(String(40), nullable=False, default="marin")
    agent_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_prompt_versions.id", ondelete="SET NULL")
    )
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    concurrent_call_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    call_start_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    call_end_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=17)
    max_call_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    max_retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    retry_delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    region_filter: Mapped[list | None] = mapped_column(JSONB)  # ilçe/şehir listesi
    sector_filter: Mapped[list | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )

    campaign_leads: Mapped[list[CampaignLead]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", lazy="noload"
    )


class CampaignLead(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "campaign_leads"
    __table_args__ = (UniqueConstraint("campaign_id", "lead_id", name="uq_campaign_lead"),)

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CampaignLeadStatus.PENDING.value, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    final_outcome: Mapped[str | None] = mapped_column(String(40))

    campaign: Mapped[Campaign] = relationship(back_populates="campaign_leads")
