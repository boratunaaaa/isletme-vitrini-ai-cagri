from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPkMixin


class InternalInvocation(Base, UUIDPkMixin):
    __tablename__ = "internal_invocations"
    __table_args__ = (
        UniqueConstraint("call_id", "external_id", name="uq_internal_invocation_call_external"),
        Index("ix_internal_invocations_call_type", "call_id", "event_type"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(20), nullable=False, default="processed")
    result_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CallTranscriptTurn(Base, UUIDPkMixin):
    __tablename__ = "call_transcript_turns"
    __table_args__ = (
        UniqueConstraint("call_id", "turn_id", name="uq_transcript_turn_call_turn"),
        Index("ix_transcript_turns_call_sequence", "call_id", "sequence"),
    )

    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False
    )
    turn_id: Mapped[str] = mapped_column(String(120), nullable=False)
    speaker: Mapped[str] = mapped_column(String(12), nullable=False)
    text_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_final: Mapped[bool] = mapped_column(nullable=False, default=True)
    sequence: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
