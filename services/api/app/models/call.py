from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import CallStatus, UsageSource

_ACTIVE_SQL = "('queued','preparing','dialing','ringing','answered','agent_active','transferring')"


class Call(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "calls"
    __table_args__ = (
        # Aynı lead için aynı anda tek aktif çağrı (DB seviyesinde garanti)
        Index(
            "uq_calls_active_lead",
            "lead_id",
            unique=True,
            postgresql_where=text(f"status IN {_ACTIVE_SQL}"),
        ),
        Index("ix_calls_campaign_status", "campaign_id", "status"),
        Index("ix_calls_started_at", "started_at"),
    )

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(80), unique=True)

    telephony_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, default="livekit_netgsm"
    )
    conversation_provider: Mapped[str] = mapped_column(
        String(40), nullable=False, default="openai_realtime"
    )
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="gpt-realtime-2.1-mini")
    voice: Mapped[str] = mapped_column(String(40), nullable=False, default="marin")
    agent_prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_prompt_versions.id", ondelete="SET NULL")
    )

    livekit_room_name: Mapped[str | None] = mapped_column(String(120), unique=True)
    provider_call_id: Mapped[str | None] = mapped_column(String(255))
    sip_call_id: Mapped[str | None] = mapped_column(String(255))

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CallStatus.QUEUED.value, index=True
    )
    outcome: Mapped[str | None] = mapped_column(String(40))

    phone_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    phone_last_four: Mapped[str | None] = mapped_column(String(4))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    disconnect_reason: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(80))

    safe_summary: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[list | None] = mapped_column(JSONB)  # retention'a tabi
    callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transfer_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    events: Mapped[list[CallEvent]] = relationship(
        back_populates="call", cascade="all, delete-orphan", lazy="noload"
    )
    usage: Mapped[CallUsage | None] = relationship(
        back_populates="call", cascade="all, delete-orphan", uselist=False, lazy="noload"
    )


class CallEvent(Base, UUIDPkMixin):
    __tablename__ = "call_events"
    __table_args__ = (Index("ix_call_events_call_ts", "call_id", "event_timestamp"),)

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    safe_payload: Mapped[dict | None] = mapped_column(JSONB)  # boyut sınırlı, PII'siz
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    call: Mapped[Call] = relationship(back_populates="events")


class CallUsage(Base, UUIDPkMixin):
    __tablename__ = "call_usage"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    input_audio_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_audio_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_audio_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_text_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_text_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_text_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    usage_source: Mapped[str] = mapped_column(
        String(12), nullable=False, default=UsageSource.PROVIDER.value
    )
    estimated_ai_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    estimated_telephony_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    estimated_total_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    call: Mapped[Call] = relationship(back_populates="usage")


class CallQualityMetrics(Base, UUIDPkMixin):
    __tablename__ = "call_quality_metrics"

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    connect_time_ms: Mapped[int | None] = mapped_column(Integer)
    first_agent_audio_ms: Mapped[int | None] = mapped_column(Integer)
    avg_response_ms: Mapped[int | None] = mapped_column(Integer)
    p95_response_ms: Mapped[int | None] = mapped_column(Integer)
    interruption_success_count: Mapped[int | None] = mapped_column(Integer)
    false_start_count: Mapped[int | None] = mapped_column(Integer)
    silence_reprompt_count: Mapped[int | None] = mapped_column(Integer)
    tool_call_success_count: Mapped[int | None] = mapped_column(Integer)
    tool_call_fail_count: Mapped[int | None] = mapped_column(Integer)
    # 1-10 arası manuel puanlar
    user_quality_score: Mapped[int | None] = mapped_column(Integer)
    tr_naturalness_score: Mapped[int | None] = mapped_column(Integer)
    understanding_score: Mapped[int | None] = mapped_column(Integer)
    sales_flow_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
