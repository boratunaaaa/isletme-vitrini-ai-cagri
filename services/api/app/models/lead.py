from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin
from app.models.enums import LeadPriority, LeadSource, LeadStatus

lead_tag_map = Table(
    "lead_tag_map",
    Base.metadata,
    Column(
        "lead_id",
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("lead_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Lead(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "leads"
    __table_args__ = (
        Index(
            "uq_leads_phone_hash",
            "phone_hash",
            unique=True,
            postgresql_where=text("phone_hash IS NOT NULL"),
        ),
        Index("ix_leads_sector_city", "sector", "city"),
        Index("ix_leads_status", "status"),
    )

    external_place_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default=LeadSource.MANUAL.value)
    business_name: Mapped[str] = mapped_column(String(500), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(500))
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)

    # PII: düz metin telefon YOK
    phone_ciphertext: Mapped[str | None] = mapped_column(Text)
    phone_hash: Mapped[str | None] = mapped_column(String(64))
    phone_last_four: Mapped[str | None] = mapped_column(String(4))
    phone_country_code: Mapped[str | None] = mapped_column(String(6))

    status: Mapped[str] = mapped_column(String(30), nullable=False, default=LeadStatus.NEW.value)
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, default=LeadPriority.NORMAL.value
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    demo_link: Mapped[str | None] = mapped_column(String(500))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    notes: Mapped[list[LeadNote]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", lazy="noload"
    )
    tags: Mapped[list[LeadTag]] = relationship(
        secondary=lead_tag_map, lazy="selectin", backref="leads"
    )


class LeadNote(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "lead_notes"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="notes")


class LeadTag(Base, UUIDPkMixin):
    __tablename__ = "lead_tags"

    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="#64748b")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )


class ImportJob(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "import_jobs"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_format: Mapped[str] = mapped_column(String(10), nullable=False)  # xlsx|csv|json
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_mapping: Mapped[dict | None] = mapped_column(JSONB)
    error_sample: Mapped[list | None] = mapped_column(JSONB)  # maskeli örnek hatalar
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
