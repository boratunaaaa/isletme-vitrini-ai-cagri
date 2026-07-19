"""`app/tasks/call_tasks.py` regresyon testleri.

PHASE_8_RESILIENCE_REPORT.md: bu dosyadaki Celery görevleri (place_call,
watchdog_check, watchdog_sweep, hangup_call) önceden HİÇ test edilmiyordu —
"redelivery güvenli bir no-op mu", "watchdog gerçekten state'i temizliyor mu"
gibi sorular yalnız kod okuyarak cevaplanabiliyordu. Gerçek Postgres + Redis
üzerinde, `TestTelephonyProvider` (ağ erişimi olmayan, deterministik sahte
provider) ile çalışır.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.core.crypto import encrypt_pii, hash_phone
from app.core.phone import normalize_phone
from app.models.call import Call
from app.models.content import AgentPromptVersion
from app.models.enums import CallStatus
from app.models.lead import Lead
from app.providers.conversation import EngineSelection
from app.providers.telephony import _test_provider
from app.services import orchestrator
from app.services.call_service import transition
from app.services.orchestrator import initiate_call
from app.tasks import call_tasks


@pytest.fixture(autouse=True)
def _reset_test_provider() -> None:
    _test_provider.created.clear()
    _test_provider.hangups.clear()
    _test_provider.fail_next = None


@pytest.fixture(autouse=True)
def safe_call_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_CALLS_ENABLED", "true")
    monkeypatch.setenv("TEST_PHONE_ALLOWLIST", "+905321234567")
    monkeypatch.setenv("DEFAULT_CALL_START_HOUR", "0")
    monkeypatch.setenv("DEFAULT_CALL_END_HOUR", "23")
    monkeypatch.setenv("MAX_CONCURRENT_CALLS", "5")
    get_settings.cache_clear()
    monkeypatch.setattr("app.services.call_service.publish_event", lambda payload: None)
    monkeypatch.setattr(orchestrator.call_policy, "check_call_hours", lambda campaign: None)


def _lead(db_session) -> Lead:
    normalized = normalize_phone("0532 123 45 67")
    lead = Lead(
        business_name="Call Task Lead",
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


def _queued_test_call(db_session) -> Call:
    _prompt(db_session)
    lead = _lead(db_session)
    call = initiate_call(
        db_session,
        lead=lead,
        selection=EngineSelection(engine="test", model="gpt-realtime-2.1-mini", voice="marin"),
        enqueue=False,
    )
    db_session.commit()
    db_session.refresh(call)
    assert call.telephony_provider == "test"
    return call


def test_place_call_dispatches_via_provider_and_transitions_to_dialing(
    db_session, clean_db
) -> None:
    call = _queued_test_call(db_session)

    call_tasks.place_call.apply(args=(str(call.id),))

    db_session.expire_all()
    refreshed = db_session.get(Call, call.id)
    assert refreshed.status == CallStatus.DIALING.value
    assert len(_test_provider.created) == 1
    assert _test_provider.created[0].call_id == str(call.id)


def test_place_call_skips_when_call_not_queued(db_session, clean_db) -> None:
    """Redelivery sonrası call zaten QUEUED değilse (örn. önceki teslimat
    başarıyla DIALING'e taşıdıysa), görev sessizce atlanmalı — ikinci bir
    dial denenmemeli."""
    call = _queued_test_call(db_session)
    transition(db_session, call, CallStatus.PREPARING)
    transition(db_session, call, CallStatus.DIALING)
    db_session.commit()

    call_tasks.place_call.apply(args=(str(call.id),))

    assert _test_provider.created == []


def test_place_call_redelivery_after_successful_dial_prevents_duplicate_real_call(
    db_session, clean_db
) -> None:
    """KRİTİK regresyon: `task_acks_late=True` altında worker, gerçek dial
    İSTEĞİ gönderildikten SONRA ama DB transaction'ı commit edilmeden ÖNCE
    çökerse, Celery görevi hâlâ-QUEUED bir satırla YENİDEN teslim eder. Bu
    test, çökmeyi simüle etmek için commit sonrası status'u manuel olarak
    QUEUED'a geri alır (Redis idempotency işareti, DB transaction'ından
    BAĞIMSIZ kalıcı olduğu için crash senaryosunu doğru temsil eder) ve
    ikinci teslimatın gerçek provider'ı TEKRAR ÇAĞIRMADIĞINI doğrular."""
    call = _queued_test_call(db_session)

    call_tasks.place_call.apply(args=(str(call.id),))
    assert len(_test_provider.created) == 1

    # Crash simülasyonu: sanki ilk transaction hiç commit olmamış gibi
    # status'u geri al (idempotency işareti Redis'te kalıcı kaldı). Görev
    # kendi AYRI session'ında commit ettiği için outer `db_session`'ın
    # identity map'i "dialing" geçişinden habersizdir — önce refresh
    # edilmezse `status = QUEUED` ataması SQLAlchemy'nin gözünde "değişiklik
    # yok" sayılıp UPDATE hiç üretilmez.
    db_session.refresh(call)
    assert call.status == CallStatus.DIALING.value
    call.status = CallStatus.QUEUED.value
    db_session.commit()

    call_tasks.place_call.apply(args=(str(call.id),))

    assert len(_test_provider.created) == 1, "İkinci teslimat gerçek dial'ı TEKRAR denememeli"
    db_session.expire_all()
    refreshed = db_session.get(Call, call.id)
    assert refreshed.status == CallStatus.FAILED.value
    assert refreshed.error_code == "duplicate_dispatch_prevented"


def test_watchdog_check_force_closes_active_call_and_hangs_up(db_session, clean_db) -> None:
    call = _queued_test_call(db_session)
    transition(db_session, call, CallStatus.PREPARING)
    transition(db_session, call, CallStatus.DIALING)
    transition(db_session, call, CallStatus.ANSWERED)
    db_session.commit()

    call_tasks.watchdog_check.apply(args=(str(call.id),))

    db_session.expire_all()
    refreshed = db_session.get(Call, call.id)
    assert refreshed.status == CallStatus.FAILED.value
    assert refreshed.disconnect_reason == "watchdog_timeout"
    assert refreshed.outcome is not None, "fallback outcome atanmalı"
    assert call.livekit_room_name in _test_provider.hangups


def test_watchdog_check_is_noop_for_already_terminal_call(db_session, clean_db) -> None:
    call = _queued_test_call(db_session)
    transition(db_session, call, CallStatus.PREPARING)
    transition(db_session, call, CallStatus.DIALING)
    transition(db_session, call, CallStatus.FAILED, reason="dispatch_failed")
    db_session.commit()

    call_tasks.watchdog_check.apply(args=(str(call.id),))

    assert _test_provider.hangups == [], "Zaten terminal olan çağrı için hangup denenmemeli"


def test_hangup_call_task_force_closes_with_user_hangup_reason(db_session, clean_db) -> None:
    call = _queued_test_call(db_session)
    transition(db_session, call, CallStatus.PREPARING)
    transition(db_session, call, CallStatus.DIALING)
    db_session.commit()

    call_tasks.hangup_call_task.apply(args=(str(call.id),), kwargs={"requested_by": "owner"})

    db_session.expire_all()
    refreshed = db_session.get(Call, call.id)
    assert refreshed.status == CallStatus.FAILED.value
    assert refreshed.disconnect_reason == "user_hangup"


def test_process_terminal_call_completes_active_call(db_session, clean_db) -> None:
    call = _queued_test_call(db_session)
    transition(db_session, call, CallStatus.PREPARING)
    transition(db_session, call, CallStatus.DIALING)
    transition(db_session, call, CallStatus.ANSWERED)
    db_session.commit()

    call_tasks.process_terminal_call.apply(args=(str(call.id),))

    db_session.expire_all()
    refreshed = db_session.get(Call, call.id)
    assert refreshed.status == CallStatus.COMPLETED.value
    assert refreshed.outcome is not None
