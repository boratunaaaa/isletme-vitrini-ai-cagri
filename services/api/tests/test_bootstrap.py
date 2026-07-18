from __future__ import annotations

import pytest
from sqlalchemy import delete, select


def test_bootstrap_owner_is_idempotent_and_hashes_password(monkeypatch, db_session):
    from app.bootstrap import bootstrap_owner
    from app.config import get_settings
    from app.db.session import get_engine, get_sessionmaker
    from app.models.user import User

    email = "owner@example.test"
    password = "StrongDevPassword123!"
    db_session.execute(delete(User).where(User.email == email))
    db_session.commit()
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", email)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", password)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    assert bootstrap_owner() == f"owner created: {email}"
    assert bootstrap_owner() == f"owner exists: {email}"

    users = db_session.scalars(select(User).where(User.email == email)).all()
    assert len(users) == 1
    assert users[0].role == "owner"
    assert users[0].password_hash != password
    assert users[0].password_hash.startswith("$argon2")


def test_bootstrap_missing_env_fails(monkeypatch):
    from app.bootstrap import bootstrap_owner
    from app.config import get_settings

    monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError):
        bootstrap_owner()
