"""initial schema

Revision ID: 20260717_0001
Revises:
Create Date: 2026-07-17 00:01:00.000000
"""

from __future__ import annotations

import app.models  # noqa: F401  # ensure all model tables are registered
from alembic import op
from app.db.base import Base

revision = "20260717_0001"
down_revision = None
branch_labels = None
depends_on = None

POST_INITIAL_TABLES = {"internal_invocations", "call_transcript_turns"}


def _initial_tables():
    return [
        table
        for name, table in Base.metadata.tables.items()
        if name not in POST_INITIAL_TABLES
    ]


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind, tables=_initial_tables())


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind, tables=list(reversed(_initial_tables())))
