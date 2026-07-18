"""Internal voice agent contract tables.

Revision ID: 20260718_0003
Revises: 20260717_0002
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260718_0003"
down_revision = "20260717_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internal_invocations",
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=20), nullable=False),
        sa.Column("result_snapshot", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], name="fk_internal_invocations_call_id_calls", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_internal_invocations"),
        sa.UniqueConstraint("call_id", "external_id", name="uq_internal_invocation_call_external"),
    )
    op.create_index(
        "ix_internal_invocations_call_type",
        "internal_invocations",
        ["call_id", "event_type"],
    )
    op.create_table(
        "call_transcript_turns",
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("turn_id", sa.String(length=120), nullable=False),
        sa.Column("speaker", sa.String(length=12), nullable=False),
        sa.Column("text_redacted", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], name="fk_call_transcript_turns_call_id_calls", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_call_transcript_turns"),
        sa.UniqueConstraint("call_id", "turn_id", name="uq_transcript_turn_call_turn"),
    )
    op.create_index(
        "ix_transcript_turns_call_sequence",
        "call_transcript_turns",
        ["call_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_turns_call_sequence", table_name="call_transcript_turns")
    op.drop_table("call_transcript_turns")
    op.drop_index("ix_internal_invocations_call_type", table_name="internal_invocations")
    op.drop_table("internal_invocations")
