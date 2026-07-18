from __future__ import annotations

import pytest

from app.config import get_settings
from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.content import AgentPromptVersion
from app.models.enums import CallStatus
from app.models.lead import Lead
from app.providers.conversation import EngineSelection
from app.services import orchestrator
from app.services.call_policy import CallPolicyError
from app.services.orchestrator import build_dial_info, initiate_call
from app.services.suppression_service import add_suppression


@pytest.fixture(autouse=True)
def safe_call_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_CALLS_ENABLED", "true")
    monkeypatch.setenv("TEST_PHONE_ALLOWLIST", "+905321234567")
    monkeypatch.setenv("DEFAULT_CALL_START_HOUR", "0")
    monkeypatch.setenv("DEFAULT_CALL_END_HOUR", "23")
    monkeypatch.setenv("MAX_CONCURRENT_CALLS", "5")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.call_service.publish_event", lambda payload: None)
    monkeypatch.setattr(orchestrator, "record_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(orchestrator.call_policy, "check_call_hours", lambda campaign: None)


def _lead(db_session) -> Lead:
    normalized = normalize_phone("0532 123 45 67")
    lead = Lead(
        business_name="Orchestrator Lead",
        phone_ciphertext=encrypt_pii(normalized.e164),
        phone_hash=hash_phone(normalized.e164),
        phone_last_four=normalized.last_four,
        phone_country_code=normalized.country_code,
    )
    db_session.add(lead)
    db_session.commit()
    db_session.refresh(lead)
    return lead


def _prompt(db_session) -> None:
    db_session.add(
        AgentPromptVersion(
            name="Active",
            system_prompt="System prompt long enough",
            opening_script="Opening script long enough",
            objective="Objective long enough",
            objection_rules="Objection rules long enough",
            is_active=True,
        )
    )
    db_session.commit()


def _selection() -> EngineSelection:
    return EngineSelection(engine="openai_realtime", model="gpt-realtime-2.1-mini", voice="marin")


def test_valid_request_creates_call_without_external_enqueue(db_session, clean_db) -> None:
    _prompt(db_session)
    lead = _lead(db_session)

    call = initiate_call(
        db_session,
        lead=lead,
        selection=_selection(),
        idempotency_key="idem-1",
        enqueue=False,
    )

    assert call.status == CallStatus.QUEUED.value
    assert call.phone_last_four == "4567"
    assert call.phone_hash == lead.phone_hash
    assert call.livekit_room_name == f"call-{call.id}"


def test_policy_rejection_does_not_create_call(
    db_session,
    clean_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prompt(db_session)
    lead = _lead(db_session)
    monkeypatch.setenv("LIVE_CALLS_ENABLED", "false")
    get_settings.cache_clear()

    with pytest.raises(CallPolicyError) as exc:
        initiate_call(db_session, lead=lead, selection=_selection(), enqueue=False)
    assert exc.value.code == "live_calls_disabled"

    assert db_session.query(orchestrator.Call).count() == 0


def test_idempotency_and_active_call_prevent_duplicates(db_session, clean_db) -> None:
    _prompt(db_session)
    lead = _lead(db_session)

    first = initiate_call(
        db_session,
        lead=lead,
        selection=_selection(),
        idempotency_key="idem-2",
        enqueue=False,
    )
    db_session.commit()
    second = initiate_call(
        db_session,
        lead=lead,
        selection=_selection(),
        idempotency_key="idem-2",
        enqueue=False,
    )
    assert second.id == first.id

    with pytest.raises(CallPolicyError) as exc:
        initiate_call(db_session, lead=lead, selection=_selection(), enqueue=False)
    assert exc.value.code == "call_in_progress"


def test_suppressed_phone_is_rejected(db_session, clean_db) -> None:
    _prompt(db_session)
    lead = _lead(db_session)
    add_suppression(
        db_session,
        phone_hash=lead.phone_hash,
        phone_last_four=lead.phone_last_four,
        reason="DNC",
        source="test",
        lead_id=lead.id,
    )
    db_session.commit()

    with pytest.raises(CallPolicyError) as exc:
        initiate_call(db_session, lead=lead, selection=_selection(), enqueue=False)
    assert exc.value.code == "suppressed"


def test_phone_is_only_revealed_in_dial_info(db_session, clean_db) -> None:
    _prompt(db_session)
    lead = _lead(db_session)
    call = initiate_call(db_session, lead=lead, selection=_selection(), enqueue=False)
    db_session.commit()

    assert "+905321234567" not in repr(call.__dict__)
    dial_info = build_dial_info(db_session, call)

    assert dial_info["phone_e164"] == "+905321234567"
    assert "+905321234567" not in dial_info["room_name"]
