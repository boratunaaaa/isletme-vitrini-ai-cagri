# CODEX_FINAL_AUDIT_PHASE_4.md

## 1. Yönetici özeti

Karar: **STAGING TESTİNE HAZIR**.

Kapsam yalnız `CODEX_AUDIT_PHASE_4_FIX.md` içinde kalan üç yüksek bulgunun kapanış kontrolüydü. Üçü de üretim kodu, SDK yüzeyi ve test kanıtıyla kapatılmış görünüyor:

- Runtime fatal error artık `recoverable is False` ile terminal oluyor; recoverable veya bilinmeyen hata görüşmeyi kapatmıyor.
- Completion retry artık permanent/transient ayrımına göre çalışıyor; kalıcı 4xx/401/403/409-conflict ilk denemede fail ediyor, geçici network/429/5xx sınırlı retry alıyor.
- SIP `sip_reason` voice-agent completion payloadından backend `/complete` endpointine taşınıyor; backend status/outcome ve campaign retry policy bunu kullanıyor.

Doğrulamalar geçti: voice-agent `107 passed`, coverage `%87`, backend `118 passed, 1 warning`, Ruff/MyPy ve Docker compose config geçti. Harici OpenAI, LiveKit, Netgsm veya telefon çağrısı yapılmadı.

## 2. Denetlenen kapsam

Okunan ana dosyalar:

- `CODEX_AUDIT_PHASE_4_FIX.md`
- `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`
- `CLAUDE_FIX_PHASE_4.md`
- `CLAUDE_AUDIT_PHASE_4.md`
- `services/voice-agent/agent/termination.py`
- `services/voice-agent/agent/api_client.py`
- `services/voice-agent/agent/job_handler.py`
- `services/voice-agent/agent/errors.py`
- `services/voice-agent/agent/models.py`
- `services/voice-agent/agent/sip.py`
- İlgili voice-agent testleri
- `services/api/app/schemas/internal/voice_agent.py`
- `services/api/app/api/routes/internal/calls.py`
- `services/api/app/services/campaign_service.py`
- `services/api/app/services/call_policy.py`
- İlgili backend testleri
- `docs/internal-voice-agent-api.md`
- `docs/voice-agent-runtime.md`

`services/voice-agent/agent/completion.py` yok; gerçek completion coordinator `services/voice-agent/agent/job_handler.py::CompletionGuard` içinde.

## 3. Git ve dosya durumu

Çalışma klasörü:

```text
/Users/kadirugur/Projects/isletme-vitrini-ai-cagri
```

Repo hâlâ ilk commit öncesi gibi tamamen untracked görünüyor. `git diff --stat` ve `git diff --name-only` boş. Bu denetimde production kodu, test, lock, migration, Docker servisleri, `.env` veya secret dosyaları değiştirilmedi.

Bu oturumda oluşturulan tek dosya:

```text
CODEX_FINAL_AUDIT_PHASE_4.md
```

## 4. Runtime error bulgusu kapanış kararı

Karar: **TAM OLARAK KAPATILDI**.

Kanıt:

- `CallTerminationWaiter._on_error()` gerçek SDK `ErrorEvent.error.recoverable` alanını okuyor (`termination.py:144-168`).
- `recoverable is False` ise `CloseReason.ERROR` set edilip waiter uyandırılıyor (`termination.py:160-167`).
- `recoverable is True` veya alan yoksa/`None` ise terminal yapılmıyor; yalnız `last_error` kaydediliyor (`termination.py:158-160`).
- Yerel SDK kaynaklarında `RealtimeModelError`, `LLMError`, `STTError`, `TTSError` sınıflarında `recoverable: bool` doğrulandı.
- `ErrorEvent.error` union’ı bu hata sınıflarını taşıyor.
- Testler fatal error, recoverable error, fatal + remote hangup, fatal + timeout, fatal + end-call yarışlarını doğruluyor (`tests/test_termination.py:61-166`).
- Job handler production path testi fatal error’da tek `openai_failure` completion, recoverable error’da pending job ve sonradan remote hangup completion doğruluyor (`tests/test_job_handler.py:263-305`).

Kalan risk: Gerçek OpenAI Realtime bağlantısında `recoverable` dağılımı staging dışında gözlenmedi; bu beklenen entegrasyon sınırı.

## 5. Completion retry bulgusu kapanış kararı

Karar: **TAM OLARAK KAPATILDI**.

Kanıt:

- `InternalAPIPermanentError` ve `InternalAPITransientError`, `InternalAPIContractError` alt sınıfları olarak ayrılmış (`errors.py:20-33`).
- API client 401/403 için retry yapmadan `InternalAPIAuthenticationError` fırlatıyor (`api_client.py:228-229`).
- 400/404/422 gibi kalıcı 4xx hatalar `InternalAPIPermanentError` oluyor ve retry edilmiyor (`api_client.py:248-255`).
- 409 duplicate conflict `DuplicateConflictError`, `CALL_NOT_DIALABLE` ise `CallNotDialableError` olarak ayrılıyor (`api_client.py:237-247`).
- 429 `Retry-After` header’ını okuyor ve `HTTP_MAX_RETRY_AFTER_SECONDS` ile üst sınıra bağlıyor (`api_client.py:62-72`, `230-235`; config `HTTP_MAX_RETRY_AFTER_SECONDS`, `config.py:38-43`).
- Timeout/transport/5xx API client retry bütçesi tükenince `InternalAPITransientError` oluyor (`api_client.py:202-221`, `256-257`).
- `CompletionGuard` yalnız `InternalAPITransientError` için retry ediyor; auth/permanent/not-dialable/duplicate conflict ve bilinmeyen exception tek denemede fail ediyor (`job_handler.py:250-294`).
- Completion event ID tüm retry denemelerinde `completion-{call_id}` olarak korunuyor (`job_handler.py:241-248`).

Test kanıtı:

- Permanent error parametrize testi tek deneme assert ediyor (`tests/test_completion_guard.py:156-177`).
- Bilinmeyen exception tek denemede fail ediyor (`tests/test_completion_guard.py:179-193`).
- Transient retry ve exhaustion testleri var (`tests/test_completion_guard.py:78-127`).
- Stable completion event ID test edilmiş (`tests/test_completion_guard.py:195-207`).
- API client 400/404/422 tek istek, 429 retry/üst sınır, 503 exhaustion testleri var (`tests/test_api_client.py:164-297`).

Not: Aynı payload idempotent completion backend tarafında 409 değil, 200 `idempotent=true` replay olarak dönüyor; conflict 409 farklı payload içindir. Bu contract mevcut idempotency helper ile uyumlu.

## 6. SIP/backend aktarımı kapanış kararı

Karar: **TAM OLARAK KAPATILDI**.

Kanıt:

- Voice-agent `CompletionIn` modelinde `sip_reason` alanı var (`agent/models.py:165-175`).
- SIP failure yolunda `complete_once(..., sip_reason=exc.reason)` çağrılıyor (`job_handler.py:371-383`).
- Backend `CompletionIn` şeması opsiyonel `sip_reason` kabul ediyor (`services/api/app/schemas/internal/voice_agent.py:307-319`).
- Backend mapping:
  - `busy -> CallStatus.BUSY`
  - `no_answer -> CallStatus.NO_ANSWER`
  - `timeout -> CallStatus.NO_ANSWER`
  - `rejected -> CallStatus.REJECTED`
  - `cancelled -> CallStatus.CANCELLED`
  (`services/api/app/api/routes/internal/calls.py:79-113`)
- Authentication/trunk/redirect/unknown gibi altyapı nedenleri bilinçli olarak terminal satış sonucu değil `FAILED` fallback’e gidiyor.
- `/complete` endpointi target status transition sonrası `derive_fallback_outcome()` ve `handle_call_terminal()` çağırıyor (`calls.py:514-538`).
- Unknown SIP reason testi `FAILED`, no-sip-reason testi backward-compatible `COMPLETED`, non-sip disconnect reason ile gelen `sip_reason` yok sayılıyor (`tests/integration/test_internal_voice_agent_api.py:538-591`).

Test kanıtı:

- Busy status ve retry scheduling (`test_complete_sip_busy_sets_call_status_and_schedules_retry`, `tests/integration/test_internal_voice_agent_api.py:475-490`).
- No-answer status (`493-505`).
- Timeout -> no-answer (`507-518`).
- Rejected status ve retry (`521-535`).
- Voice-agent completion payloadına `sip_reason` eklenmesi (`tests/test_job_handler.py:311-334`).

## 7. Campaign terminal/retry entegrasyonu

Karar: entegrasyon yeterli.

Kanıt:

- `/complete` artık inline campaign lead güncellemesi yerine `handle_call_terminal(db, call)` ve `maybe_complete_campaign(db, call.campaign_id)` çağırıyor (`calls.py:531-538`).
- `handle_call_terminal()` campaign’siz çağrılarda güvenli dönüyor (`campaign_service.py:118-119`).
- Campaign veya campaign lead bulunamazsa completion kaybolmadan güvenli dönüyor (`campaign_service.py:120-128`).
- Idempotency: campaign lead `CALLING` değilse ikinci kez işlenmiyor (`campaign_service.py:129-130`).
- Retry planı `compute_next_retry()` üzerinden call status/outcome, attempt count, campaign max retry ve callback zamanını kullanıyor (`campaign_service.py:132-158`, `call_policy.py:148-175`).
- Busy/no-answer/rejected retry çarpanları mevcut (`call_policy.py:125-132`).
- Wrong number, do-not-call, demo requested gibi terminal outcomes otomatik retry üretmiyor (`call_policy.py:134-166`, `tests/unit/test_retry.py:38-63`).
- Callback requested callback zamanını kullanıyor (`tests/unit/test_retry.py:66-79`).
- Aynı completion event ID replay olduğunda `idempotent()` handler’ı tekrar çalıştırmıyor (`internal_contract.py:75-110`); completion idempotency entegrasyon testi var (`tests/integration/test_internal_voice_agent_api.py:395-436`).

Kalan küçük not: Max retry sonrası entegrasyon testi doğrudan `/complete` path’inde yok; retry helper max sınırı test ediyor. Bu staging blocker değil, ilave regresyon testi olarak eklenebilir.

## 8. Test kalitesi

Yeni testlerin kanıt değeri iyi:

- Runtime error testleri hem `CallTerminationWaiter` hem job handler production path’i kullanıyor.
- Completion retry testleri `CompletionGuard` ve typed exception sınıflandırmasını doğrudan assert ediyor.
- API client testleri gerçek `httpx.AsyncClient` + custom transport ile HTTP status davranışını doğruluyor.
- SIP/backend testleri FastAPI internal endpoint production route’unu kullanıyor; yalnız helper fonksiyonunu test etmiyor.
- Campaign retry testleri `/complete` ile `handle_call_terminal()` yan etkisini busy/rejected için gözlüyor.

Mock/fake sınırı:

- Gerçek LiveKit/OpenAI/SIP network lifecycle hâlâ staging credential gerektiriyor.
- 429 ve SIP status davranışı fake transport / test route ile doğrulandı; gerçek provider/proxy davranışı staging’de izlenmeli.
- `agent/main.py` coverage hâlâ `%0`; bu önceki düşük risk ve bu kapanış kapsamının dışında.

## 9. Yeni kritik bulgular

Yeni **KRİTİK** bulgu yok.

## 10. Yeni yüksek bulgular

Yeni **YÜKSEK** bulgu yok.

## 11. Orta ve düşük bulgular

Yeni staging blocker yok.

Kalan düşük/orta notlar:

- `/complete` path’inde max retry sonrası campaign lead final status için daha doğrudan entegrasyon testi eklenebilir.
- `SIPTimeoutError.reason="timeout"` hâlâ `SIP_FAILURE_REASONS` frozenset içinde listelenmiyor; runtime davranışı çalışıyor, dokümante set eksikliği düşük risk.
- `agent/main.py` otomatik test coverage `%0`; manuel config validation ve Docker config bunu kısmen kapatıyor.

## 12. Çalıştırılan doğrulamalar

Voice-agent:

```text
PYTHONPYCACHEPREFIX=/tmp/ivac_final_pycache_voice uv run python -m compileall -q agent
RUFF_CACHE_DIR=/tmp/ivac_final_ruff_voice uv run ruff check agent tests
MYPY_CACHE_DIR=/tmp/ivac_final_mypy_voice PYTHONPYCACHEPREFIX=/tmp/ivac_final_pycache_voice uv run mypy agent
PYTHONPYCACHEPREFIX=/tmp/ivac_final_pycache_voice uv run pytest -q -o cache_dir=/tmp/ivac_final_pytest_voice
COVERAGE_FILE=/tmp/ivac_final_voice_coverage PYTHONPYCACHEPREFIX=/tmp/ivac_final_pycache_voice uv run pytest --cov=agent --cov-report=term-missing -o cache_dir=/tmp/ivac_final_pytest_voice_cov
```

Sonuç:

```text
compileall: geçti
ruff: All checks passed!
mypy: Success: no issues found in 16 source files
pytest: 107 passed in 14.77s
coverage: TOTAL 87%, 107 passed
```

Backend:

```text
RUFF_CACHE_DIR=/tmp/ivac_final_ruff_api uv run ruff check app tests
MYPY_CACHE_DIR=/tmp/ivac_final_mypy_api PYTHONPYCACHEPREFIX=/tmp/ivac_final_pycache_api uv run mypy app
PYTHONPYCACHEPREFIX=/tmp/ivac_final_pycache_api uv run pytest -q -o cache_dir=/tmp/ivac_final_pytest_api
```

Sonuç:

```text
ruff: All checks passed!
mypy: Success: no issues found in 80 source files
pytest: 118 passed, 1 warning in 22.12s
```

Docker:

```text
docker compose -f docker-compose.dev.yml config
docker compose -f docker-compose.dev.yml --profile voice config
```

Sonuç:

```text
normal config: geçti, voice-agent varsayılan profilde yok
voice profile config: geçti, voice-agent yalnız --check-config komutuyla görünüyor
```

## 13. Staging öncesi kalan işlemler

- Staging secrets ve internal token güvenli secret store üzerinden tanımlanmalı.
- İlk gerçek test yalnız allowlist test numarasıyla yapılmalı.
- LiveKit SIP outbound trunk önceden staging ortamında hazırlanmalı; bu kod oturumu trunk oluşturmadı.
- İlk staging koşusunda şu telemetry özellikle izlenmeli: `recoverable` error eventleri, `/complete` idempotency, SIP `sip_reason`, campaign lead retry status, PII-safe logs.

## 14. Sonuç kararı

**STAGING TESTİNE HAZIR**

Gerekçe:

- Üç yüksek bulgu tamamen kapandı.
- Yeni kritik/yüksek bulgu bulunmadı.
- Voice-agent testleri, backend testleri, Ruff, MyPy ve Docker config geçti.
- Harici servis çağrısı yapılmadan doğrulanabilecek alanlar doğrulandı.
- Geriye yalnız gerçek credential ile kontrollü staging entegrasyon testi kaldı.

## 15. Değiştirilen dosyalar

```text
CODEX_FINAL_AUDIT_PHASE_4.md
```
