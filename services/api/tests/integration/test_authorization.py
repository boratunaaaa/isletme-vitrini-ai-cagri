from __future__ import annotations

from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.content import AgentPromptVersion
from app.models.lead import Lead
from app.models.ops import DemoRequest
from app.models.system import AuditLog


def _lead(db_session) -> Lead:
    normalized = normalize_phone("0532 123 45 67")
    lead = Lead(
        business_name="Auth Lead",
        phone_ciphertext=encrypt_pii(normalized.e164),
        phone_hash=hash_phone(normalized.e164),
        phone_last_four=normalized.last_four,
        phone_country_code=normalized.country_code,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


def test_anonymous_requests_to_protected_endpoints_get_401(client) -> None:
    assert client.get("/api/leads").status_code == 401
    assert client.get("/api/live/events").status_code == 401


def test_viewer_cannot_mutate_or_reveal_phone(client, login_as, db_session) -> None:
    lead = _lead(db_session)
    headers = login_as(role="viewer")

    assert client.get("/api/leads").status_code == 200
    update = client.patch(
        f"/api/leads/{lead.id}",
        headers=headers,
        json={"business_name": "X"},
    )
    assert update.status_code == 403
    assert client.post(f"/api/leads/{lead.id}/reveal-phone", headers=headers).status_code == 403


def test_owner_can_reveal_phone_and_audit_is_written(client, login_as, db_session) -> None:
    lead = _lead(db_session)
    headers = login_as(role="owner")

    response = client.post(f"/api/leads/{lead.id}/reveal-phone", headers=headers)

    assert response.status_code == 200
    assert response.json()["phone_e164"] == "+905321234567"
    audit = db_session.query(AuditLog).filter(AuditLog.action == "leads.phone_reveal").one()
    assert audit.safe_metadata is None


def test_reveal_phone_is_rate_limited_per_user(client, login_as, db_session) -> None:
    """PHASE_9_SECURITY_REPORT.md: ele geçirilmiş yetkili bir hesabın script
    ile tüm veritabanını tek tek numara açığa çıkararak sızdırmasını
    zorlaştırmak için kullanıcı-başına 60/60s limit uygulanır."""
    lead = _lead(db_session)
    headers = login_as(role="owner")

    for _ in range(60):
        response = client.post(f"/api/leads/{lead.id}/reveal-phone", headers=headers)
        assert response.status_code == 200

    limited = client.post(f"/api/leads/{lead.id}/reveal-phone", headers=headers)
    assert limited.status_code == 429


def test_campaign_suppression_and_prompt_authorization(client, login_as, db_session) -> None:
    lead = _lead(db_session)
    viewer_headers = login_as(role="viewer", email="viewer2@example.test")
    viewer_suppression = client.post(
        "/api/suppression",
        headers=viewer_headers,
        json={"lead_id": str(lead.id), "reason": "DNC"},
    )
    assert viewer_suppression.status_code == 403

    owner_headers = login_as(role="owner", email="owner2@example.test")
    campaign = client.post("/api/campaigns", headers=owner_headers, json={"name": "Owner Campaign"})
    assert campaign.status_code == 201
    suppression = client.post(
        "/api/suppression",
        headers=owner_headers,
        json={"lead_id": str(lead.id), "reason": "DNC"},
    )
    assert suppression.status_code == 201

    prompt = AgentPromptVersion(
        name="Auth Prompt",
        system_prompt="System prompt long enough",
        opening_script="Opening script long enough",
        objective="Objective text long enough",
        objection_rules="Objection rules long enough",
    )
    db_session.add(prompt)
    db_session.commit()
    assert (
        client.post(f"/api/prompts/{prompt.id}/activate", headers=viewer_headers).status_code == 403
    )
    assert (
        client.post(f"/api/prompts/{prompt.id}/activate", headers=owner_headers).status_code == 200
    )


def test_sales_agent_cannot_manage_users(client, login_as) -> None:
    headers = login_as(role="sales_agent")

    response = client.post(
        "/api/users",
        headers=headers,
        json={
            "email": "new@example.test",
            "full_name": "New User",
            "password": "StrongPassword123!",
            "role": "viewer",
        },
    )

    assert response.status_code == 403


def test_sales_agent_cannot_reveal_phone_via_demo_wa_link(client, login_as, db_session) -> None:
    """PHASE_9_SECURITY_REPORT.md: `demo_wa_link` önceden `CALL_INITIATE`
    gerektiriyordu — bu, `PHONE_REVEAL` yetkisi OLMAYAN `sales_agent`'ın tam
    açık telefon numarasını farklı-yetkili bir endpoint üzerinden almasına
    izin veren gerçek bir RBAC sınırı ihlaliydi (dedicated `reveal-phone`
    doğru şekilde 403 dönüyordu, bu endpoint dönmüyordu)."""
    lead = _lead(db_session)
    demo = DemoRequest(lead_id=lead.id)
    db_session.add(demo)
    db_session.commit()
    db_session.refresh(demo)

    sales_headers = login_as(role="sales_agent")
    response = client.get(f"/api/demo-requests/{demo.id}/wa-link", headers=sales_headers)
    assert response.status_code == 403

    owner_headers = login_as(role="owner", email="owner-walink@example.test")
    response = client.get(f"/api/demo-requests/{demo.id}/wa-link", headers=owner_headers)
    assert response.status_code == 200
    assert "905321234567" in response.json()["wa_link"]
