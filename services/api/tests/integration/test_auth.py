from __future__ import annotations

import hashlib
import json
import time

from app.core.security import SESSION_COOKIE, verify_password
from app.models.user import User


def test_login_creates_session_and_wrong_password_does_not(
    client, create_user, redis_client, db_session
) -> None:
    user = create_user(email="login@example.test", password="StrongPassword123!", role="owner")

    bad = client.post(
        "/api/auth/login",
        json={"email": "login@example.test", "password": "WrongPassword123!"},
    )
    assert bad.status_code == 401
    assert bad.cookies.get(SESSION_COOKIE) is None

    good = client.post(
        "/api/auth/login",
        json={"email": "login@example.test", "password": "StrongPassword123!"},
    )
    assert good.status_code == 200
    token = good.cookies.get(SESSION_COOKIE)
    assert token
    session_key = "session:" + hashlib.sha256(token.encode()).hexdigest()
    assert redis_client.ttl(session_key) > 0

    stored = db_session.get(User, user.id)
    assert stored is not None
    assert not verify_password(stored.password_hash, "WrongPassword123!")


def test_distributed_brute_force_triggers_account_level_lockout(client, create_user) -> None:
    """PHASE_9_SECURITY_REPORT.md: eskiden yalnız `{ip}:{email}` anahtarı
    vardı — kaynak IP'sini döndüren bir saldırgan her IP için TAZE bir sayaç
    aldığı için tek bir bilinen hesabı dağıtık şekilde brute-force etmek
    fiilen sınırsızdı. Hesap-seviyeli (yalnız e-posta) ikinci bir kilit,
    HİÇ kullanılmamış yeni bir IP'den bile isteği reddetmeli."""
    create_user(email="distributed@example.test", password="StrongPassword123!", role="owner")

    for i in range(20):
        response = client.post(
            "/api/auth/login",
            json={"email": "distributed@example.test", "password": "WrongPassword123!"},
            headers={"X-Forwarded-For": f"203.0.113.{i}"},
        )
        assert response.status_code == 401

    # 21. deneme, hiç kullanılmamış TAMAMEN YENİ bir IP'den geliyor ama
    # hesap-seviyeli sayaç (20 eşiği) tetiklenmeli.
    locked = client.post(
        "/api/auth/login",
        json={"email": "distributed@example.test", "password": "StrongPassword123!"},
        headers={"X-Forwarded-For": "203.0.113.250"},
    )
    assert locked.status_code == 429


def test_inactive_user_cannot_login(client, create_user) -> None:
    create_user(email="inactive@example.test", password="StrongPassword123!", is_active=False)

    response = client.post(
        "/api/auth/login",
        json={"email": "inactive@example.test", "password": "StrongPassword123!"},
    )

    assert response.status_code == 403


def test_csrf_and_logout_session_lifecycle(client, login_as) -> None:
    headers = login_as(role="owner")

    assert client.get("/health").status_code == 200
    no_csrf = client.patch("/api/leads/00000000-0000-0000-0000-000000000001", json={})
    assert no_csrf.status_code == 403
    assert (
        client.patch(
            "/api/leads/00000000-0000-0000-0000-000000000001",
            headers={"x-csrf-token": "wrong"},
            json={},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/leads/00000000-0000-0000-0000-000000000001",
            headers=headers,
            json={},
        ).status_code
        == 404
    )

    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(client, login_as, redis_client) -> None:
    login_as(role="owner")
    token = client.cookies.get(SESSION_COOKIE)
    assert token
    key = "session:" + hashlib.sha256(token.encode()).hexdigest()
    raw = json.loads(redis_client.get(key))
    raw["absolute_expiry"] = time.time() - 1
    redis_client.set(key, json.dumps(raw), ex=60)

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert redis_client.get(key) is None
