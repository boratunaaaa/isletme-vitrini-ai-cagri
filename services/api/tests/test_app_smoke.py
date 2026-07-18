from __future__ import annotations

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
