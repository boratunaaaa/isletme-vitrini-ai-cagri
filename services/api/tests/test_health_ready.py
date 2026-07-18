from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_ok_and_no_sensitive_details():
    from app.main import app

    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    body = response.text.lower()
    assert "postgresql" not in body
    assert "redis://" not in body
    assert "secret" not in body


def test_ready_ok_when_dependencies_ok(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "_check_database", lambda: "ok")
    monkeypatch.setattr(main, "_check_redis", lambda: "ok")
    response = TestClient(main.app).get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_ready_non_2xx_when_dependency_fails(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main, "_check_database", lambda: "error")
    monkeypatch.setattr(main, "_check_redis", lambda: "ok")
    response = TestClient(main.app).get("/ready")
    assert response.status_code == 503
    payload = response.json()
    assert payload == {"status": "not_ready", "checks": {"database": "error", "redis": "ok"}}
    body = response.text.lower()
    assert "postgresql" not in body
    assert "redis://" not in body
    assert "secret" not in body
