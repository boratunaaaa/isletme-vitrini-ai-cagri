"""Sistem tabloları: entegrasyon ayarları (secret İÇERMEZ) ve audit log."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPkMixin


class IntegrationSetting(Base, UUIDPkMixin):
    __tablename__ = "integration_settings"
    __table_args__ = (
        UniqueConstraint("provider", "setting_key", name="uq_integration_setting"),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    setting_key: Mapped[str] = mapped_column(String(80), nullable=False)
    safe_value: Mapped[str | None] = mapped_column(String(500))  # secret ASLA yazılmaz
    is_configured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=datetime.utcnow,
        nullable=False,
    )


class AuditLog(Base, UUIDPkMixin):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_created", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    safe_metadata: Mapped[dict | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
