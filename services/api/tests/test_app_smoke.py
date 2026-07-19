from __future__ import annotations

import pytest
from fastapi import FastAPI


def test_app_imports_and_openapi_builds():
    from app.main import app

    assert isinstance(app, FastAPI)
    assert app.title == "İşletme Vitrini AI Çağrı Merkezi API"
    schema = app.openapi()
    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]
    assert "/api/auth/login" in schema["paths"]
    assert "/api/leads" in schema["paths"]
    assert "/api/campaigns" in schema["paths"]
    assert "/api/calls" in schema["paths"]
    assert "/api/live/events" in schema["paths"]


def test_docs_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """PHASE_9_SECURITY_REPORT.md: /docs, /redoc, /openapi.json önceden
    yalnız Caddy'nin proxy kurallarıyla dışarıya kapalıydı — uygulama
    seviyesinde tek bir savunma katmanı yoktu. Production'da bunlar
    uygulama kodunda da kapatılmalı (derinlemesine savunma)."""
    from app.config import Settings
    from app.main import create_app

    prod_settings = Settings.model_validate(
        {
            "APP_ENV": "production",
            "APP_URL": "https://panel.example.com",
            "DATABASE_URL": "postgresql+psycopg://user:pass@host:5432/db",
            "JWT_SECRET": "a" * 40,
            "COOKIE_SECRET": "a" * 40,
            "PII_ENCRYPTION_KEY": "a" * 40,
            "PHONE_HASH_PEPPER": "a" * 40,
            "INTERNAL_SERVICE_TOKEN": "a" * 40,
        }
    )
    monkeypatch.setattr("app.main.get_settings", lambda: prod_settings)

    app = create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_docs_enabled_outside_production() -> None:
    from app.main import create_app

    app = create_app()

    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"
