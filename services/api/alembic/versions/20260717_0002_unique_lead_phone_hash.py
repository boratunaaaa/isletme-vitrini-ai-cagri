"""Enforce unique lead phone hash.

Revision ID: 20260717_0002
Revises: 20260717_0001
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "20260717_0002"
down_revision = "20260717_0001"
branch_labels = None
depends_on = None


def _indexes() -> set[str]:
    inspector = inspect(op.get_bind())
    return {idx["name"] for idx in inspector.get_indexes("leads")}


def upgrade() -> None:
    indexes = _indexes()
    if "ix_leads_phone_hash" in indexes:
        op.drop_index("ix_leads_phone_hash", table_name="leads")
    if "uq_leads_phone_hash" not in indexes:
        op.create_index(
            "uq_leads_phone_hash",
            "leads",
            ["phone_hash"],
            unique=True,
            postgresql_where=sa.text("phone_hash IS NOT NULL"),
        )


def downgrade() -> None:
    indexes = _indexes()
    if "uq_leads_phone_hash" in indexes:
        op.drop_index("uq_leads_phone_hash", table_name="leads")
    if "ix_leads_phone_hash" not in indexes:
        op.create_index("ix_leads_phone_hash", "leads", ["phone_hash"])
