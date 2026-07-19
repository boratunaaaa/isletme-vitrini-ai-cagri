from __future__ import annotations

from decimal import Decimal

from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.enums import CallOutcome, CallStatus
from app.models.lead import Lead
from app.models.pricing import ProviderPricing


def _lead(db_session, *, status: str = "new") -> Lead:
    normalized = normalize_phone("0532 123 45 67")
    lead = Lead(
        business_name="System Test Lead",
        phone_ciphertext=encrypt_pii(normalized.e164),
        phone_hash=hash_phone(normalized.e164),
        phone_last_four=normalized.last_four,
        phone_country_code=normalized.country_code,
        status=status,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


def _pricing(db_session) -> ProviderPricing:
    row = ProviderPricing(
        provider="openai",
        model="gpt-realtime-2.1-mini",
        input_audio_price_per_million=Decimal("32.0000"),
        cached_audio_price_per_million=Decimal("0.4000"),
        output_audio_price_per_million=Decimal("64.0000"),
        input_text_price_per_million=Decimal("5.0000"),
        cached_text_price_per_million=Decimal("2.5000"),
        output_text_price_per_million=Decimal("20.0000"),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_dashboard_stats_visible_to_viewer(client, login_as) -> None:
    headers = login_as(role="viewer")

    response = client.get("/api/dashboard/stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["calls_today"] == 0
    assert body["live_calls"] == 0
    assert "gates" in body and "live_calls_enabled" in body["gates"]
    assert isinstance(body["integrations"], list)
    assert len(body["integrations"]) >= 1


def test_dashboard_stats_counts_do_not_call_leads(client, login_as, db_session) -> None:
    _lead(db_session, status="do_not_call")
    headers = login_as(role="owner")

    response = client.get("/api/dashboard/stats", headers=headers)

    assert response.status_code == 200
    assert response.json()["do_not_call_count"] == 1


def test_dashboard_stats_requires_authentication(client) -> None:
    assert client.get("/api/dashboard/stats").status_code == 401


def test_pricing_list_requires_settings_read(client, login_as, db_session) -> None:
    _pricing(db_session)
    # NOT: TestClient tek bir çerez kavanozu paylaşır — her login_as() çağrısı
    # aktif oturum çerezini DEĞİŞTİRİR. Bu yüzden her rolün isteği, o rol için
    # login_as() çağrıldıktan HEMEN SONRA (başka bir login_as'tan önce) yapılmalı.
    viewer_headers = login_as(role="viewer")
    assert client.get("/api/pricing", headers=viewer_headers).status_code == 403

    owner_headers = login_as(role="owner", email="owner-pricing@example.test")
    owner_response = client.get("/api/pricing", headers=owner_headers)
    assert owner_response.status_code == 200
    assert owner_response.json()[0]["input_audio_price_per_million"] == "32.0000"


def test_pricing_update_only_owner_admin_and_persists_decimal(client, login_as, db_session) -> None:
    pricing = _pricing(db_session)
    agent_headers = login_as(role="sales_agent")
    forbidden = client.patch(
        f"/api/pricing/{pricing.id}",
        headers=agent_headers,
        json={"output_audio_price_per_million": "70.0000"},
    )
    assert forbidden.status_code == 403

    owner_headers = login_as(role="owner", email="owner-pricing-2@example.test")
    updated = client.patch(
        f"/api/pricing/{pricing.id}",
        headers=owner_headers,
        json={"output_audio_price_per_million": "70.0000"},
    )
    assert updated.status_code == 200
    assert updated.json()["output_audio_price_per_million"] == "70.0000"


def test_pricing_update_rejects_invalid_decimal(client, login_as, db_session) -> None:
    pricing = _pricing(db_session)
    owner_headers = login_as(role="owner", email="owner-pricing-3@example.test")

    response = client.patch(
        f"/api/pricing/{pricing.id}",
        headers=owner_headers,
        json={"output_audio_price_per_million": "not-a-number"},
    )

    assert response.status_code == 422


def test_settings_list_returns_editable_keys_even_when_unset(client, login_as) -> None:
    headers = login_as(role="admin")

    response = client.get("/api/settings", headers=headers)

    assert response.status_code == 200
    keys = {(item["provider"], item["setting_key"]) for item in response.json()}
    assert ("billing", "usd_try_rate") in keys
    assert all(not item["is_configured"] for item in response.json())


def test_settings_update_rejects_non_allowlisted_key(client, login_as) -> None:
    headers = login_as(role="owner")

    response = client.patch(
        "/api/settings",
        headers=headers,
        json={"provider": "openai", "setting_key": "api_key", "value": "sk-test"},
    )

    assert response.status_code == 422


def test_settings_update_persists_and_is_audited(client, login_as, db_session) -> None:
    from app.models.system import AuditLog

    headers = login_as(role="owner")

    response = client.patch(
        "/api/settings",
        headers=headers,
        json={"provider": "billing", "setting_key": "usd_try_rate", "value": "34.50"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["safe_value"] == "34.50"
    assert body["is_configured"] is True
    audit = db_session.query(AuditLog).filter(AuditLog.action == "settings.update").one()
    assert audit.resource_id == "billing.usd_try_rate"


def test_audit_logs_requires_audit_read_permission(client, login_as) -> None:
    agent_headers = login_as(role="sales_agent")
    assert client.get("/api/audit-logs", headers=agent_headers).status_code == 403

    owner_headers = login_as(role="owner", email="owner-audit@example.test")
    response = client.get("/api/audit-logs", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "total" in body
    # login_as çağrısının kendisi audit yazmaz ama login sırasında yazılan
    # herhangi bir kayıt varsa toplam sayı negatif olmamalı
    assert body["total"] >= 0


def test_dashboard_reflects_call_cost_and_outcomes(client, login_as, db_session) -> None:
    from datetime import UTC, datetime

    from app.models.call import Call, CallUsage

    lead = _lead(db_session)
    call = Call(
        lead_id=lead.id,
        telephony_provider="livekit_sip",
        conversation_provider="openai_realtime",
        model="gpt-realtime-2.1-mini",
        voice="marin",
        status=CallStatus.COMPLETED.value,
        outcome=CallOutcome.INTERESTED.value,
        answered_at=datetime.now(UTC),
        duration_seconds=120,
    )
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)
    usage = CallUsage(
        call_id=call.id,
        provider="openai",
        model="gpt-realtime-2.1-mini",
        estimated_ai_cost=Decimal("0.1200"),
        estimated_telephony_cost=Decimal("0.0300"),
        estimated_total_cost=Decimal("0.1500"),
    )
    db_session.add(usage)
    db_session.commit()

    headers = login_as(role="owner", email="owner-dashcost@example.test")
    response = client.get("/api/dashboard/stats", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["calls_today"] == 1
    assert body["answered_today"] == 1
    assert body["interested_count"] == 1
    assert body["total_cost_today_usd"] == "0.150000"
    assert body["avg_duration_seconds"] == 120
