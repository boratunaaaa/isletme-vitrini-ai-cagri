from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import delete

from alembic import command

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://ivac:ivac@localhost:5432/ivac_test")
os.environ.setdefault("DATABASE_URL_TEST", os.environ["DATABASE_URL"])
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-minimum-32-characters")
os.environ.setdefault("COOKIE_SECRET", "test-cookie-secret-minimum-32-characters")
os.environ.setdefault("PII_ENCRYPTION_KEY", "test-pii-secret-minimum-32-characters")
os.environ.setdefault("PHONE_HASH_PEPPER", "test-phone-pepper-minimum-32-characters")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token-minimum-32-characters")
os.environ.setdefault("TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")


def alembic_config() -> Config:
    return Config("alembic.ini")


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[None]:
    from app.config import get_settings
    from app.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture()
def db_session(migrated_db):
    from app.db.session import get_sessionmaker

    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture()
def redis_client(migrated_db):
    from app.core.redis import get_redis

    redis = get_redis()
    redis.flushdb()
    yield redis
    redis.flushdb()


@pytest.fixture()
def clean_db(db_session, redis_client):
    from app.models.call import Call, CallEvent, CallQualityMetrics, CallUsage
    from app.models.campaign import Campaign, CampaignLead
    from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
    from app.models.internal import CallTranscriptTurn, InternalInvocation
    from app.models.lead import ImportJob, Lead, LeadNote, LeadTag, lead_tag_map
    from app.models.ops import Callback, DemoRequest, SuppressionEntry
    from app.models.pricing import ProviderPricing
    from app.models.system import AuditLog, IntegrationSetting
    from app.models.user import User

    ordered = (
        CallQualityMetrics,
        CallUsage,
        CallEvent,
        CallTranscriptTurn,
        DemoRequest,
        Callback,
        InternalInvocation,
        SuppressionEntry,
        CampaignLead,
        Call,
        Campaign,
        ImportJob,
        LeadNote,
        LeadTag,
        Lead,
        AgentPromptVersion,
        KnowledgeBaseEntry,
        ProviderPricing,
        IntegrationSetting,
        AuditLog,
        User,
    )
    db_session.rollback()
    db_session.execute(delete(lead_tag_map))
    for model in ordered:
        db_session.execute(delete(model))
    db_session.commit()
    yield
    db_session.rollback()
    db_session.execute(delete(lead_tag_map))
    for model in ordered:
        db_session.execute(delete(model))
    db_session.commit()


@pytest.fixture()
def client(clean_db) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def create_user(db_session) -> Callable[..., object]:
    from app.core.security import hash_password
    from app.models.user import User

    def _create_user(
        *,
        email: str = "owner@example.test",
        password: str = "StrongPassword123!",
        role: str = "owner",
        is_active: bool = True,
    ) -> User:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=email.split("@", 1)[0],
            role=role,
            is_active=is_active,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        return user

    return _create_user


@pytest.fixture()
def login_as(client: TestClient, create_user) -> Callable[..., dict[str, str]]:
    def _login_as(
        *,
        role: str = "owner",
        email: str | None = None,
        password: str = "StrongPassword123!",
        is_active: bool = True,
    ) -> dict[str, str]:
        user_email = email or f"{role}@example.test"
        create_user(email=user_email, password=password, role=role, is_active=is_active)
        response = client.post("/api/auth/login", json={"email": user_email, "password": password})
        assert response.status_code == 200
        csrf_token = response.cookies.get("ivac_csrf")
        assert csrf_token
        return {"x-csrf-token": csrf_token}

    return _login_as


@pytest.fixture()
def clean_seed_rows(db_session):
    from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
    from app.models.pricing import ProviderPricing
    from app.models.system import IntegrationSetting

    for model in (AgentPromptVersion, KnowledgeBaseEntry, ProviderPricing, IntegrationSetting):
        db_session.execute(delete(model))
    db_session.commit()
    yield
    for model in (AgentPromptVersion, KnowledgeBaseEntry, ProviderPricing, IntegrationSetting):
        db_session.execute(delete(model))
    db_session.commit()
