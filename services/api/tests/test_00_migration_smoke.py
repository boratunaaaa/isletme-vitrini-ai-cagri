from __future__ import annotations

from sqlalchemy import inspect

from alembic import command
from tests.conftest import alembic_config


def test_alembic_upgrade_downgrade_round_trip():
    from app.db.session import get_engine

    config = alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    inspector = inspect(get_engine())
    tables = set(inspector.get_table_names())
    assert {
        "users",
        "leads",
        "campaigns",
        "campaign_leads",
        "calls",
        "call_events",
        "provider_pricing",
        "knowledge_base_entries",
        "agent_prompt_versions",
        "audit_logs",
    }.issubset(tables)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
