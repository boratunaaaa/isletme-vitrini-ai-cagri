from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import get_settings
from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.call import Call, CallEvent, CallUsage
from app.models.campaign import Campaign, CampaignLead
from app.models.content import AgentPromptVersion, KnowledgeBaseEntry
from app.models.enums import CallOutcome, CallStatus, CampaignLeadStatus
from app.models.internal import CallTranscriptTurn, InternalInvocation
from app.models.lead import Lead
from app.models.ops import Callback, DemoRequest, SuppressionEntry
from app.models.pricing import ProviderPricing

TOKEN = "internal-current-token-minimum-32-chars"
PREVIOUS = "internal-previous-token-minimum-32-chars"


@pytest.fixture(autouse=True)
def internal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN_PREVIOUS", PREVIOUS)
    monkeypatch.setenv("INTERNAL_SERVICE_NAME", "voice-agent")
    monkeypatch.setenv("LIVE_CALLS_ENABLED", "true")
    monkeypatch.setenv("TEST_PHONE_ALLOWLIST", "+905321234567")
    monkeypatch.setenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID", "trunk-safe-id")
    monkeypatch.setenv("NETGSM_OUTBOUND_NUMBER", "+902160000000")
    monkeypatch.setenv("NETGSM_SIP_PASSWORD", "should-not-leak")
    get_settings.cache_clear()


@pytest.fixture()
def internal_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "X-Request-ID": "phase3-request"}


def _prompt(db_session) -> AgentPromptVersion:
    prompt = AgentPromptVersion(
        name=f"Internal Prompt {uuid.uuid4()}",
        system_prompt="System prompt long enough",
        opening_script="Opening script long enough",
        objective="Objective text long enough",
        objection_rules="Objection rules long enough",
        is_active=True,
    )
    db_session.add(prompt)
    db_session.flush()
    return prompt


def _lead(db_session, raw_phone: str = "0532 123 45 67") -> Lead:
    normalized = normalize_phone(raw_phone)
    lead = Lead(
        business_name="Internal Lead",
        sector="Kafe",
        city="İstanbul",
        district="Üsküdar",
        website="https://example.test",
        demo_link="https://demo.example.test/internal",
        phone_ciphertext=encrypt_pii(normalized.e164),
        phone_hash=hash_phone(normalized.e164),
        phone_last_four=normalized.last_four,
        phone_country_code=normalized.country_code,
    )
    db_session.add(lead)
    db_session.flush()
    return lead


def _call(
    db_session,
    *,
    status: CallStatus = CallStatus.QUEUED,
    raw_phone: str = "0532 123 45 67",
    room_name: str | None = None,
) -> Call:
    prompt = _prompt(db_session)
    lead = _lead(db_session, raw_phone)
    db_session.add(KnowledgeBaseEntry(category="hizmet", title="Hizmet", content="Güvenli bilgi."))
    db_session.add(KnowledgeBaseEntry(category="paketler", title="Paket", content="1.990 TL."))
    call = Call(
        lead_id=lead.id,
        status=status.value,
        model="gpt-realtime-2.1-mini",
        voice="marin",
        agent_prompt_version_id=prompt.id,
        phone_hash=lead.phone_hash,
        phone_last_four=lead.phone_last_four,
        livekit_room_name=room_name or f"call-{uuid.uuid4()}",
    )
    db_session.add(call)
    db_session.commit()
    db_session.refresh(call)
    return call


def _pricing(db_session) -> None:
    db_session.add(
        ProviderPricing(
            provider="openai",
            model="gpt-realtime-2.1-mini",
            input_audio_price_per_million=Decimal("10"),
            cached_audio_price_per_million=Decimal("1"),
            output_audio_price_per_million=Decimal("20"),
            input_text_price_per_million=Decimal("5"),
            cached_text_price_per_million=Decimal("0.5"),
            output_text_price_per_million=Decimal("15"),
            is_active=True,
        )
    )
    db_session.commit()


def test_internal_auth_current_previous_and_session_isolation(
    client,
    internal_headers,
    login_as,
) -> None:
    assert client.get("/api/internal/v1/health").status_code == 401
    assert (
        client.get("/api/internal/v1/health", headers={"Authorization": "Bearer bad"}).status_code
        == 401
    )
    assert client.get("/api/internal/v1/health", headers=internal_headers).status_code == 200
    assert (
        client.get(
            "/api/internal/v1/health",
            headers={"Authorization": f"Bearer {PREVIOUS}"},
        ).status_code
        == 200
    )
    login_as(role="owner")
    assert client.get("/api/internal/v1/health").status_code == 401


def test_bootstrap_returns_safe_context_and_rejects_suppressed_terminal(
    client,
    db_session,
    clean_db,
    internal_headers,
) -> None:
    call = _call(db_session)

    response = client.get(f"/api/internal/v1/calls/{call.id}/bootstrap", headers=internal_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["phone_e164"] == "+905321234567"
    assert body["agent_configuration"]["prompt_version_id"]
    assert "should-not-leak" not in str(body)
    assert "INTERNAL_SERVICE_TOKEN" not in str(body)

    db_session.add(
        SuppressionEntry(
            phone_hash=call.phone_hash,
            phone_last_four=call.phone_last_four,
            reason="DNC",
            source="test",
        )
    )
    db_session.commit()
    suppressed = client.get(f"/api/internal/v1/calls/{call.id}/bootstrap", headers=internal_headers)
    assert suppressed.status_code == 403
    assert suppressed.json()["error"]["code"] == "SUPPRESSED_PHONE"

    terminal = _call(db_session, status=CallStatus.COMPLETED, raw_phone="0555 111 22 33")
    terminal_response = client.get(
        f"/api/internal/v1/calls/{terminal.id}/bootstrap",
        headers=internal_headers,
    )
    assert terminal_response.status_code == 409


def test_dial_plan_policy_and_no_credential_leak(
    client,
    db_session,
    clean_db,
    internal_headers,
) -> None:
    call = _call(db_session, status=CallStatus.PREPARING, room_name="call-fixed")

    response = client.get(f"/api/internal/v1/calls/{call.id}/dial-plan", headers=internal_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["phone_e164"] == "+905321234567"
    assert body["room_name"] == "call-fixed"
    assert body["participant_identity"] == f"phone-{call.id}"
    assert "should-not-leak" not in str(body)


def test_events_are_idempotent_conflicting_and_redacted(
    client,
    db_session,
    clean_db,
    internal_headers,
) -> None:
    call = _call(db_session, status=CallStatus.PREPARING)
    payload = {
        "event_id": "evt-1",
        "event_type": "dialing",
        "occurred_at": datetime.now(UTC).isoformat(),
        "sequence": 1,
        "payload": {"phone": "+905321234567", "safe": "ok"},
    }

    first = client.post(
        f"/api/internal/v1/calls/{call.id}/events", headers=internal_headers, json=payload
    )
    second = client.post(
        f"/api/internal/v1/calls/{call.id}/events", headers=internal_headers, json=payload
    )
    changed = {**payload, "sequence": 2}
    conflict = client.post(
        f"/api/internal/v1/calls/{call.id}/events", headers=internal_headers, json=changed
    )

    assert first.status_code == 200
    assert second.json()["idempotent"] is True
    assert conflict.status_code == 409
    event = db_session.query(CallEvent).filter(CallEvent.event_type == "dialing").one()
    assert event.safe_payload["payload"]["phone"] == "[redacted]"


def test_transcript_storage_redaction_and_disabled(
    client,
    db_session,
    clean_db,
    internal_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call = _call(db_session)
    payload = {
        "turn_id": "turn-1",
        "speaker": "user",
        "text": "Telefonum +90 532 123 45 67 ve mail a@example.test",
        "started_at": datetime.now(UTC).isoformat(),
        "ended_at": (datetime.now(UTC) + timedelta(seconds=1)).isoformat(),
        "is_final": True,
        "sequence": 1,
    }

    response = client.post(
        f"/api/internal/v1/calls/{call.id}/transcript-turns",
        headers=internal_headers,
        json=payload,
    )
    duplicate = client.post(
        f"/api/internal/v1/calls/{call.id}/transcript-turns",
        headers=internal_headers,
        json=payload,
    )
    invalid = client.post(
        f"/api/internal/v1/calls/{call.id}/transcript-turns",
        headers=internal_headers,
        json={
            **payload,
            "turn_id": "bad-turn",
            "ended_at": "2026-07-18T00:00:00+00:00",
            "started_at": "2026-07-18T00:00:10+00:00",
        },
    )

    assert response.status_code == 200
    assert duplicate.json()["idempotent"] is True
    assert invalid.status_code == 422
    turn = db_session.query(CallTranscriptTurn).one()
    assert "+905321234567" not in turn.text_redacted
    assert "[redacted-email]" in turn.text_redacted

    monkeypatch.setenv("TRANSCRIPT_STORAGE_ENABLED", "false")
    get_settings.cache_clear()
    disabled = client.post(
        f"/api/internal/v1/calls/{call.id}/transcript-turns",
        headers=internal_headers,
        json={**payload, "turn_id": "turn-disabled"},
    )
    assert disabled.json()["status"] == "ignored"


def test_usage_update_idempotent_decimal_and_pricing_required(
    client,
    db_session,
    clean_db,
    internal_headers,
) -> None:
    call = _call(db_session)
    _pricing(db_session)
    payload = {
        "usage_event_id": "usage-1",
        "provider": "openai",
        "model": "gpt-realtime-2.1-mini",
        "input_audio_tokens": 1000,
        "output_audio_tokens": 1000,
        "occurred_at": datetime.now(UTC).isoformat(),
    }

    first = client.post(
        f"/api/internal/v1/calls/{call.id}/usage", headers=internal_headers, json=payload
    )
    duplicate = client.post(
        f"/api/internal/v1/calls/{call.id}/usage", headers=internal_headers, json=payload
    )
    negative = client.post(
        f"/api/internal/v1/calls/{call.id}/usage",
        headers=internal_headers,
        json={**payload, "usage_event_id": "usage-bad", "input_audio_tokens": -1},
    )

    assert first.status_code == 200
    assert first.json()["estimated_ai_cost_usd"] == "0.030000"
    assert duplicate.json()["idempotent"] is True
    assert negative.status_code == 422
    assert db_session.query(CallUsage).one().estimated_ai_cost == Decimal("0.030000")


def _tool_payload(tool_call_id: str) -> dict:
    return {"tool_call_id": tool_call_id, "occurred_at": datetime.now(UTC).isoformat()}


@pytest.mark.parametrize(
    "path",
    [
        "get-service-information",
        "get-package-information",
        "mark-interested",
        "mark-not-interested",
        "mark-wrong-number",
        "mark-decision-maker-unavailable",
        "end-call-safely",
    ],
)
def test_simple_tools_success(client, db_session, clean_db, internal_headers, path: str) -> None:
    call = _call(db_session, status=CallStatus.AGENT_ACTIVE)

    response = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/{path}",
        headers=internal_headers,
        json=_tool_payload(f"tool-{path}"),
    )

    assert response.status_code == 200
    assert "should-not-leak" not in str(response.json())


def test_mutating_tools_duplicate_and_failures(
    client, db_session, clean_db, internal_headers
) -> None:
    call = _call(db_session, status=CallStatus.AGENT_ACTIVE)
    callback_at = datetime.now(UTC) + timedelta(days=1)

    demo_payload = {**_tool_payload("demo-1"), "requested_channel": "whatsapp"}
    demo = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/request-demo-link",
        headers=internal_headers,
        json=demo_payload,
    )
    demo_dup = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/request-demo-link",
        headers=internal_headers,
        json=demo_payload,
    )
    callback = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/schedule-callback",
        headers=internal_headers,
        json={**_tool_payload("cb-1"), "callback_at": callback_at.isoformat()},
    )
    suppression = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/add-to-suppression-list",
        headers=internal_headers,
        json={**_tool_payload("sup-1"), "reason": "do not call"},
    )
    transfer = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/request-human-transfer",
        headers=internal_headers,
        json=_tool_payload("transfer-1"),
    )

    assert demo.status_code == 200
    assert demo_dup.json()["idempotent"] is True
    assert callback.status_code == 200
    assert suppression.status_code == 200
    assert transfer.json()["result"]["transfer_available"] is False
    assert db_session.query(DemoRequest).count() == 1
    assert db_session.query(Callback).count() == 1
    assert db_session.query(SuppressionEntry).count() == 1


def test_finalize_conflict_and_completion_idempotency(
    client,
    db_session,
    clean_db,
    internal_headers,
) -> None:
    call = _call(db_session, status=CallStatus.AGENT_ACTIVE)
    finalize = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/finalize-call-outcome",
        headers=internal_headers,
        json={**_tool_payload("fin-1"), "outcome": "interested", "safe_summary": "safe"},
    )
    conflict = client.post(
        f"/api/internal/v1/calls/{call.id}/tools/finalize-call-outcome",
        headers=internal_headers,
        json={**_tool_payload("fin-2"), "outcome": "wrong_number"},
    )
    completion_payload = {
        "completion_event_id": "complete-1",
        "disconnect_reason": "remote_hangup",
        "ended_at": datetime.now(UTC).isoformat(),
        "duration_seconds": 180,
    }
    complete = client.post(
        f"/api/internal/v1/calls/{call.id}/complete",
        headers=internal_headers,
        json=completion_payload,
    )
    complete_dup = client.post(
        f"/api/internal/v1/calls/{call.id}/complete",
        headers=internal_headers,
        json=completion_payload,
    )

    assert finalize.status_code == 200
    assert conflict.status_code == 409
    assert complete.status_code == 200
    assert complete_dup.json()["idempotent"] is True
    db_session.refresh(call)
    assert call.status == CallStatus.COMPLETED.value
    assert call.outcome == CallOutcome.INTERESTED.value
    assert db_session.query(InternalInvocation).count() >= 2


# ─── SIP terminal sonucu -> backend status/outcome/retry (CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-3) ──


def _campaign_with_lead(db_session, call: Call, *, max_retry_count: int = 2) -> CampaignLead:
    """Call'u aktif bir kampanyaya CALLING durumunda bağlar ki `/complete`'in
    retry-scheduling etkisi (compute_next_retry) gözlemlenebilsin."""
    campaign = Campaign(name=f"SIP mapping test {uuid.uuid4()}", max_retry_count=max_retry_count)
    db_session.add(campaign)
    db_session.flush()
    call.campaign_id = campaign.id
    campaign_lead = CampaignLead(
        campaign_id=campaign.id,
        lead_id=call.lead_id,
        status=CampaignLeadStatus.CALLING.value,
        attempt_count=0,
    )
    db_session.add(campaign_lead)
    db_session.commit()
    db_session.refresh(call)
    return campaign_lead


def _complete(client, internal_headers, call_id, *, event_id: str, sip_reason: str | None):
    payload = {
        "completion_event_id": event_id,
        "disconnect_reason": "sip_failure",
        "ended_at": datetime.now(UTC).isoformat(),
        "duration_seconds": 0,
    }
    if sip_reason is not None:
        payload["sip_reason"] = sip_reason
    return client.post(
        f"/api/internal/v1/calls/{call_id}/complete", headers=internal_headers, json=payload
    )


def test_complete_sip_busy_sets_call_status_and_schedules_retry(
    client, db_session, clean_db, internal_headers
) -> None:
    call = _call(db_session, status=CallStatus.DIALING)
    campaign_lead = _campaign_with_lead(db_session, call)

    response = _complete(client, internal_headers, call.id, event_id="c-busy", sip_reason="busy")

    assert response.status_code == 200
    db_session.refresh(call)
    db_session.refresh(campaign_lead)
    assert call.status == CallStatus.BUSY.value
    assert campaign_lead.status == CampaignLeadStatus.RETRY_SCHEDULED.value
    assert campaign_lead.next_attempt_at is not None
    assert campaign_lead.next_attempt_at > datetime.now(UTC)
    assert campaign_lead.attempt_count == 1


def test_complete_sip_no_answer_sets_call_status(
    client, db_session, clean_db, internal_headers
) -> None:
    call = _call(db_session, status=CallStatus.RINGING)

    response = _complete(
        client, internal_headers, call.id, event_id="c-no-answer", sip_reason="no_answer"
    )

    assert response.status_code == 200
    db_session.refresh(call)
    assert call.status == CallStatus.NO_ANSWER.value


def test_complete_sip_timeout_maps_to_no_answer(
    client, db_session, clean_db, internal_headers
) -> None:
    call = _call(db_session, status=CallStatus.DIALING)

    response = _complete(
        client, internal_headers, call.id, event_id="c-timeout", sip_reason="timeout"
    )

    assert response.status_code == 200
    db_session.refresh(call)
    assert call.status == CallStatus.NO_ANSWER.value


def test_complete_sip_rejected_sets_call_status_and_slower_retry(
    client, db_session, clean_db, internal_headers
) -> None:
    call = _call(db_session, status=CallStatus.RINGING)
    campaign_lead = _campaign_with_lead(db_session, call)

    response = _complete(
        client, internal_headers, call.id, event_id="c-rejected", sip_reason="rejected"
    )

    assert response.status_code == 200
    db_session.refresh(call)
    db_session.refresh(campaign_lead)
    assert call.status == CallStatus.REJECTED.value
    assert campaign_lead.status == CampaignLeadStatus.RETRY_SCHEDULED.value


def test_complete_sip_unknown_reason_falls_back_to_failed(
    client, db_session, clean_db, internal_headers
) -> None:
    """`authentication_error`/`trunk_error`/vb. — müşteri/numara kaynaklı
    olmayan altyapı hataları — bilerek eşlenmez, mevcut FAILED fallback'i
    korunur (backend contract'ında yeni bir status EKLENMEDİ)."""
    call = _call(db_session, status=CallStatus.DIALING)

    response = _complete(
        client, internal_headers, call.id, event_id="c-trunk", sip_reason="trunk_error"
    )

    assert response.status_code == 200
    db_session.refresh(call)
    assert call.status == CallStatus.FAILED.value


def test_complete_without_sip_reason_still_completes_normally(
    client, db_session, clean_db, internal_headers
) -> None:
    """Geriye dönük uyumluluk: `sip_reason` gönderilmeyen (veya sip_failure
    dışı) eski davranış değişmemeli."""
    call = _call(db_session, status=CallStatus.AGENT_ACTIVE)

    response = _complete(client, internal_headers, call.id, event_id="c-none", sip_reason=None)

    assert response.status_code == 200
    db_session.refresh(call)
    assert call.status == CallStatus.COMPLETED.value


def test_complete_sip_reason_ignored_for_non_sip_disconnect_reason(
    client, db_session, clean_db, internal_headers
) -> None:
    """`sip_reason` yalnız `disconnect_reason == "sip_failure"` iken anlamlı;
    başka bir disconnect_reason ile birlikte gelirse yok sayılmalı."""
    call = _call(db_session, status=CallStatus.AGENT_ACTIVE)
    payload = {
        "completion_event_id": "c-ignore-sip-reason",
        "disconnect_reason": "remote_hangup",
        "ended_at": datetime.now(UTC).isoformat(),
        "duration_seconds": 42,
        "sip_reason": "busy",
    }

    response = client.post(
        f"/api/internal/v1/calls/{call.id}/complete", headers=internal_headers, json=payload
    )

    assert response.status_code == 200
    db_session.refresh(call)
    assert call.status == CallStatus.COMPLETED.value
