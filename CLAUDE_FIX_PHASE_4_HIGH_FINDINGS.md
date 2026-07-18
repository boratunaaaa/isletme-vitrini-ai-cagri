# CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md — Codex'in 3 Yüksek Bulgusunun Düzeltilmesi

Kapsam: `CODEX_AUDIT_PHASE_4_FIX.md`'nin **"ÖNEMLİ DÜZELTMELER GEREKLİ"** kararındaki 3 YÜKSEK bulgunun (runtime error terminal, completion retry sınıflandırması, SIP terminal sonucunun backend status/outcome/retry'e taşınması) düzeltilmesi. `services/voice-agent/**` + gerekli minimum backend contract genişlemesi (`services/api/app/schemas/internal/voice_agent.py`, `services/api/app/api/routes/internal/calls.py`) + ilgili testler + doküman/status dosyaları değiştirildi. Frontend geliştirilmedi, deployment yapılmadı, commit/push yapılmadı, gerçek OpenAI/LiveKit/Netgsm bağlantısı veya telefon araması kurulmadı, `.env`/secret dosyası açılmadı, proje dışı AI memory dosyaları değiştirilmedi.

## 1. Yönetici özeti

Codex'in üç YÜKSEK bulgusunun tamamı düzeltildi ve testle kanıtlandı. (1) Runtime `error` event'i artık gerçek SDK alanı `recoverable: bool`'a göre sınıflandırılıyor — yalnız KESİN fatal hatalar (`recoverable=False`) terminal sayılıyor, kurtarılabilir hatalar görüşmeyi gereksiz yere bitirmiyor. (2) `CompletionGuard` artık yalnız GERÇEKTEN geçici hataları (`InternalAPITransientError`) retry ediyor; 401/403/404/409-conflict/422 gibi kalıcı hatalar ilk denemede fail ediyor, 429 `Retry-After`'a uyarak sınırlı retry ediyor. (3) SIP busy/no_answer/rejected/cancelled artık backend'de gerçek call status'una taşınıyor VE — denetimde bulunan ek bir kök neden sayesinde — kampanya retry zamanlaması da düzeldi: `/complete` endpoint'i artık her zaman koşulsuz "completed" yazan eski inline kodu değil, mevcut (ve zaten doğru olan) `campaign_service.handle_call_terminal()`'i çağırıyor. Voice-agent testleri 83'ten 107'ye, backend testleri 111'den 118'e çıktı; hiçbir mevcut test bozulmadı.

## 2. Codex'in üç yüksek bulgusu

`CODEX_AUDIT_PHASE_4_FIX.md`'den (bölüm 23):

- **YÜKSEK-1**: `termination.py:99-130, 143-147` — `_on_error()` yalnız `last_error` kaydediyor, `_close_event` set etmiyor. Fatal realtime error close event üretmezse job `max_call_duration_seconds`'a kadar açık kalıyor, hata `timeout` gibi raporlanabiliyor.
- **YÜKSEK-2**: `job_handler.py:237-247` — `CompletionGuard` `except Exception as exc` ile TÜM hataları retry ediyor; `InternalAPIAuthenticationError`/`InternalAPIContractError` gibi kalıcı 401/403/422 sınıfları üst katmanda ayırt edilmiyor. Yanlış token/schema bug'ında 3 kez gereksiz `/complete` denemesi.
- **YÜKSEK-3**: `job_handler.py:333-344`, `calls.py:72-77, 478-491`, `call_service.py:127-168` — SIP reason event payload'ında var ama backend call status/outcome buna göre değişmiyor; completion her SIP hatasında `sip_failure`→backend'de `failed`'a düşüyor. Satış tekrar politikası için busy/cevapsız/reddedildi ayrımı kayboluyor.

## 3. Runtime error terminal düzeltmesi

`services/voice-agent/agent/termination.py::CallTerminationWaiter._on_error()` yeniden yazıldı. Gerçek SDK kaynağından doğrulanan mekanizma kullanıldı:

- `livekit/agents/voice/agent_activity.py::_on_error()` her `LLMError`/`RealtimeModelError`/`STTError`/`TTSError`'ı koşulsuz `session.emit("error", ErrorEvent(error=..., source=...))` ile yayınlıyor.
- Her dört hata sınıfı da (`livekit/agents/llm/realtime.py`, `stt/stt.py`, `tts/tts.py` içinde) `recoverable: bool` alanı taşıyor.
- OpenAI plugin'inde (`livekit/plugins/openai/realtime/realtime_model.py`) `_emit_error(error, recoverable)` çağrı yerleri incelendi: bağlantı/protokol hatalarında `recoverable=False` (satır 924, 927, 944), OpenAI'ın kendi döndürdüğü toparlanabilir hata mesajlarında `recoverable=True` (satır 2098) kullanılıyor.

Yeni `_on_error()`: `recoverable is False` VE `_close_event` henüz set edilmemişse → terminal (`CloseReason.ERROR` → `DisconnectReason.OPENAI_FAILURE`). `recoverable is True` veya bilinmiyorsa (`None`) → terminal DEĞİL, yalnız `last_error` olarak kaydedilir (mevcut davranış korunur).

## 4. Fatal/non-fatal error sınıflandırması

| `recoverable` | Davranış | Kanıt |
|---|---|---|
| `False` | Terminal — `DisconnectReason.OPENAI_FAILURE` ile job biter | `test_fatal_realtime_error_terminates_with_openai_failure` |
| `True` | Terminal DEĞİL — SDK kendi içinde toparlanır, görüşme devam eder | `test_recoverable_realtime_error_does_not_terminate` |
| Bilinmiyor (`None`/attribute yok) | Terminal DEĞİL (güvenli varsayılan — false-positive terminasyon riski false-negative'den daha kötü) | Kod yolu: `getattr(error, "recoverable", None)`, yalnız `is False` kontrolü |

Sınıflandırma kaynağı SDK'nın kendi verisi olduğu için LiveKit/OpenAI'a özel bir varsayım UYDURULMADI — yalnız gerçek, introspection ile doğrulanmış bir alan okunuyor.

## 5. Completion retry sınıflandırması

`services/voice-agent/agent/errors.py`'ye iki yeni sınıf eklendi:

- `InternalAPIPermanentError(InternalAPIContractError)` — kalıcı 4xx sözleşme reddi.
- `InternalAPITransientError(InternalAPIContractError)` — `api_client.py`'nin kendi iç retry bütçesi TÜKENDİKTEN SONRA fırlatılır.

`services/voice-agent/agent/api_client.py::_handle_response()` yeniden sınıflandırıldı:

- 401/403 → `InternalAPIAuthenticationError` (değişmedi, zaten kalıcı).
- 409 `DUPLICATE_EVENT_CONFLICT` → `DuplicateConflictError` (değişmedi).
- 409 `CALL_NOT_DIALABLE` / diğer 4xx `CALL_NOT_DIALABLE` → `CallNotDialableError` (değişmedi).
- 409 diğer / 400-499 diğer (400/404/422/vb.) → **artık** `InternalAPIPermanentError` (öncekinde genel `InternalAPIContractError`).
- Response şeması uyuşmazlığı / geçersiz JSON → **artık** `InternalAPIPermanentError` (aynı istek tekrar edilse de sonuç değişmez).
- 5xx → değişmedi, `httpx.TransportError` fırlatılıp `_request()`'in kendi retry döngüsüne düşer.
- **YENİ**: 429 → `_RateLimitedSignal(retry_after_seconds)` — `_request()` bunu timeout/transport ile AYNI deneme bütçesinde, `Retry-After` header'ına uyarak (üst sınır `HTTP_MAX_RETRY_AFTER_SECONDS`, varsayılan 30s, testlerde küçük değere ayarlanabilir) retry eder.
- Tüm deneme bütçesi tükenirse (yalnız timeout/transport/429 döngüsünden) → **artık** `InternalAPITransientError` (öncekinde `InternalAPIContractError`).

`InternalAPIPermanentError`/`InternalAPITransientError` ikisi de `InternalAPIContractError`'ın alt sınıfı olduğu için, bu iki tipi ayırt etmeyen mevcut genel `except InternalAPIContractError`/`except Exception` blokları (ör. `events.py`/`transcript.py`'nin arka plan consumer'ları) hiçbir değişiklik gerektirmeden çalışmaya devam ediyor.

`services/voice-agent/agent/job_handler.py::CompletionGuard.complete_once()` yeniden yazıldı: retry döngüsü artık `except InternalAPITransientError` (retry) ile `except (InternalAPIAuthenticationError, InternalAPIPermanentError, CallNotDialableError, DuplicateConflictError)` (tek deneme, hemen fail) arasında açıkça ayrım yapıyor. Sınıflandırılamayan/beklenmeyen bir exception tipi de güvenli varsayılan olarak TEK denemede fail ediyor — "her hatayı retry et" orijinal hatasının farklı bir exception sınıfıyla tekrarlanmasını önlüyor.

## 6. Permanent HTTP hata davranışı

401/403/400/404/422/409-conflict → **tek deneme**, `CompletionGuard._exhausted=True`, açık `logger.error` (hata sınıfı adı + redakte mesaj) + `CompletionError` fırlatılır. Test kanıtı: `test_permanent_errors_are_not_retried` (`InternalAPIAuthenticationError`, `InternalAPIPermanentError`, `CallNotDialableError`, `DuplicateConflictError` — 4 parametrize senaryo, hepsi `api.attempts == 1`), `test_permanent_4xx_not_retried` (`api_client.py` seviyesinde 400/404/422, `len(transport.requests) == 1`), `test_call_not_dialable_4xx_not_retried`.

## 7. Transient HTTP hata davranışı

Network timeout/connection reset/5xx → `api_client.py`'nin kendi iç retry bütçesi (backoff'lu) tüketilir, sonra `InternalAPITransientError` fırlatılır, `CompletionGuard` bunu KENDİ backoff'uyla (0.5s/1s/2s, 3 denemeye kadar) tekrar dener. 429 → `Retry-After`'a uyarak (üst sınırlı) `api_client.py` seviyesinde retry edilir. Test kanıtı: `test_retries_transient_failures_then_succeeds`, `test_503_exhausted_retries_raise_transient_error_not_contract_error`, `test_429_retried_with_retry_after_then_success`, `test_429_exhausted_retries_raise_transient_error`, `test_429_retry_after_capped_at_upper_bound` (999999s header, `HTTP_MAX_RETRY_AFTER_SECONDS=0.05` ile testte saniyeler içinde doğrulandı — üretimde varsayılan 30s).

## 8. SIP terminal sonucu eşlemesi

Backend `CompletionIn` şemasına (`services/api/app/schemas/internal/voice_agent.py`) opsiyonel `sip_reason: str | None` alanı eklendi (geriye dönük uyumlu — eski voice-agent sürümü göndermezse davranış değişmez). `services/voice-agent/agent/models.py::CompletionIn`'e aynı alan eklendi; `job_handler.py`'nin SIP hata yolu artık `complete_once(..., sip_reason=exc.reason)` çağırıyor.

`services/api/app/api/routes/internal/calls.py`'de `_SIP_REASON_TO_STATUS` eşlemesi eklendi:

| `sip_reason` | Backend `CallStatus` |
|---|---|
| `busy` | `BUSY` |
| `no_answer` | `NO_ANSWER` |
| `timeout` | `NO_ANSWER` (yanıt hiç gelmedi — aynı aile) |
| `rejected` | `REJECTED` |
| `cancelled` | `CANCELLED` |
| `authentication_error`/`trunk_error`/`redirect_unsupported`/`unknown_sip_failure` | (eşlenmez) → mevcut `FAILED` fallback korunur |

`CallStatus` enum'u ve `CALL_STATUS_TRANSITIONS` state machine'i (`services/api/app/models/enums.py`) BUSY/NO_ANSWER/REJECTED/CANCELLED'ı zaten DIALING/RINGING'den geçerli terminal hedef olarak destekliyordu (Phase 1-2'de kurulmuştu) — bug bu kapasitenin hiç KULLANILMAMASIYDI, yeni enum değeri veya migration GEREKMEDİ.

## 9. Backend status/outcome aktarımı

`complete_call()`'ın `handle()` closure'ı: `_target_status_for_completion(payload)` ile hedef statü SIP reason'a göre seçilir, `transition(db, call, target_status, ...)` denenir; state machine reddederse (ör. call zaten ANSWERED'ken busy'e geçmeye çalışmak — pratikte oluşmaz çünkü SIP hatası her zaman answer'dan ÖNCE gerçekleşir) mevcut `FAILED` fallback'i korunur. `call.outcome is None` ise `derive_fallback_outcome()` (değişmedi) yeni, doğru `call.status`'u okuyarak daha isabetli bir outcome üretir.

## 10. Campaign retry uyumu

Denetim sırasında bulunan İKİNCİL kök neden: `/complete`'in campaign_lead güncellemesi (`link.status = CampaignLeadStatus.COMPLETED.value` — koşulsuz, HER completion'da) hiçbir zaman `campaign_service.compute_next_retry()`'yi çağırmıyordu — bu fonksiyon yalnız Celery worker'ın (Phase 1-2, farklı bir orkestrasyon yolu) kullandığı `handle_call_terminal()` içinden erişilebiliyordu. Bu, SIP status düzeltmesi TEK BAŞINA bile retry zamanlamasının hiçbir zaman gerçek policy'yi kullanmayacağı anlamına geliyordu.

Düzeltme: `/complete`'in inline campaign_lead bloğu kaldırıldı, yerine mevcut (ve zaten doğru test edilmiş) `campaign_service.handle_call_terminal(db, call)` + `maybe_complete_campaign(db, call.campaign_id)` çağrısı kondu. Bu, `Lead.status`/`last_contacted_at` güncellemesini de (önceden `/complete` hiç yapmıyordu) yan etki olarak düzeltti. Test kanıtı: `test_complete_sip_busy_sets_call_status_and_schedules_retry` (campaign_lead → `RETRY_SCHEDULED`, `next_attempt_at` gelecekte, `attempt_count == 1`), `test_complete_sip_rejected_sets_call_status_and_slower_retry`.

## 11. Internal API contract değişiklikleri

- `CompletionIn.sip_reason: str | None = None` (backend + voice-agent, ikisi de) — **eklendi**, yalnız opsiyonel yeni alan, mevcut alanlar değişmedi, migration GEREKMEDİ (DB şeması etkilenmedi, yalnız Pydantic request şeması).
- `docs/internal-voice-agent-api.md`'ye yeni "## Completion" bölümü eklendi (örnek payload + `sip_reason` açıklaması + backward-compat notu).
- Diğer tüm endpoint/şema alanları (`disconnect_reason`, `status`, `outcome`, `error_code`, `duration_seconds`, event type'ları) DEĞİŞMEDİ.

## 12. Değiştirilen production dosyaları

```text
services/voice-agent/agent/termination.py     (_on_error fatal/non-fatal ayrımı)
services/voice-agent/agent/session.py         (FakeRealtimeSession error-event simülasyon yardımcıları)
services/voice-agent/agent/errors.py          (InternalAPIPermanentError, InternalAPITransientError)
services/voice-agent/agent/api_client.py      (429/Retry-After, permanent/transient sınıflandırma — tam yeniden yazım)
services/voice-agent/agent/config.py          (+HTTP_MAX_RETRY_AFTER_SECONDS)
services/voice-agent/agent/job_handler.py     (CompletionGuard retry sınıflandırması, sip_reason iletimi)
services/voice-agent/agent/models.py          (CompletionIn.sip_reason)
services/api/app/schemas/internal/voice_agent.py  (CompletionIn.sip_reason)
services/api/app/api/routes/internal/calls.py     (_SIP_REASON_TO_STATUS, handle_call_terminal çağrısı)
```

## 13. Eklenen testler

- `tests/test_termination.py`: +7 (fatal/recoverable error, 2 ayrı fatal hatanın yalnız ilkinin sayılması, fatal-error'ın remote-hangup/timeout/end-call ile yarışları).
- `tests/test_completion_guard.py`: +6 (4 permanent tip parametrize + bilinmeyen tip + completion event ID stabilitesi + final-failure log testi); mevcut 2 test yeni `fail_with=` parametresiyle güncellendi.
- `tests/test_api_client.py`: +7 (permanent 4xx parametrize, CALL_NOT_DIALABLE 4xx, 429 başarı, 429 tükenme, 429 üst sınır, 503 tükenme→transient tip).
- `tests/test_job_handler.py`: +2 (fatal realtime error → tek completion, recoverable error → job aktif kalır) + mevcut SIP busy testine `sip_reason` completion-payload assertion'ı eklendi.
- `services/api/tests/integration/test_internal_voice_agent_api.py`: +7 (busy→status+retry, no_answer, timeout→no_answer, rejected→status+retry, bilinmeyen sip_reason→failed fallback, sip_reason'sız geriye dönük uyumluluk, sip_reason'ın yalnız sip_failure ile birlikte anlamlı olması).

## 14. Voice-agent test sonucu

```text
uv run pytest -q
107 passed in ~11-14s
```

(1. düzeltme sonrası: 83 passed.)

## 15. Coverage sonucu

```text
uv run pytest --cov=agent --cov-report=term-missing
107 passed, TOTAL %87
```

(1. düzeltme sonrası: %86.) Öne çıkan artışlar: `api_client.py` %78→%84, `errors.py` %82 (yeni sınıflar kısmen dolaylı test edildi), `termination.py` %94→%96, `job_handler.py` %85→%86. `sip.py` hâlâ düşük (%59) — gerçek ağ çağrısı gerektiren dallar bu oturumda da bilerek test edilmedi (yasak). `agent/main.py` hâlâ %0 (Phase 4 denetim bulgusu değil, bilinen pre-existing boşluk).

## 16. Ruff sonucu

```text
uv run ruff check agent tests
All checks passed!
```

## 17. MyPy sonucu

```text
uv run mypy agent
Success: no issues found in 16 source files
```

## 18. Backend regresyon sonucu

```text
cd services/api
uv run ruff check app tests   → All checks passed!
uv run mypy app                → Success: no issues found in 80 source files
uv run pytest -q               → 118 passed, 1 warning (öncekinde 111 — 7 yeni SIP-mapping testi, hiçbiri bozulmadı)
```

## 19. Docker doğrulama sonucu

```text
docker compose -f docker-compose.dev.yml config -q                    → geçti
docker compose -f docker-compose.dev.yml --profile voice config -q    → geçti
```

`docker-compose.dev.yml`/Dockerfile'a bu oturumda dokunulmadı.

## 20. Kalan kritik bulgular

Yok.

## 21. Kalan yüksek bulgular

Codex'in raporladığı 3 YÜKSEK bulgunun hiçbiri açık kalmadı. Bilinen ORTA/DÜŞÜK bulgular (Codex'in kendi raporunda, bu oturumun kapsamı DIŞINDA bırakıldı — talimat yalnız 3 yüksek bulguyu kapsıyordu):

- **ORTA-1**: End-call kapanış cümlesi `SpeechHandle` yerine `agent_state_changed`+grace penceresiyle bekleniyor — daha kesin bir speech-completion sinyali (`SpeechHandle.wait_for_playout()`, gerçek SDK'da var, kaynakta doğrulandı) ileride kullanılabilir.
- **ORTA-2**: `_report_final_usage()`'daki bir `send_usage()` hatası, zaten doğru hesaplanmış `termination.reason`'ı `agent_error`'a düşürebilir (generic except bloğu üzerinden). Bu oturumda DOKUNULMADI çünkü Codex'in 3 YÜKSEK bulgusuna dahil değildi.
- **ORTA-3**: `events.py`/`transcript.py`'nin `stop()` metodunda `queue.join()` için explicit graceful timeout yok.
- **DÜŞÜK-1**: `agent/main.py` CLI wrapper'ı hâlâ 0% coverage.
- **DÜŞÜK-2** (Codex): `SIPTimeoutError.reason="timeout"` `SIP_FAILURE_REASONS` frozenset'inde listelenmiyor (kod çalışıyor, yalnız dokümante set eksik) — bu oturumda dokunulmadı.

## 22. Credential olmadan doğrulanamayanlar

- Gerçek bir OpenAI Realtime bağlantısının GERÇEKTEN `recoverable=True/False` değerini ne sıklıkla/ne zaman ürettiği (yalnız SDK kaynak kodundaki `_emit_error` çağrı yerleri statik olarak incelendi).
- 429/`Retry-After` davranışının gerçek backend/proxy'den nasıl geldiği (yalnız `httpx` transport mock'u ile test edildi).
- SIP status kodlarının GERÇEK Netgsm trunk'tan beklendiği gibi gelip gelmediği (yalnız RFC 3261 anlamları + `SipCallError` attribute'ları statik doğrulandı).
- `campaign_service.handle_call_terminal()`'in gerçek bir kampanya koşusunda (Celery `campaign_tick` ile) `/complete` yoluyla da doğru tetiklendiği — yalnız birim/entegrasyon testleriyle (gerçek worker olmadan) doğrulandı.

## 23. Staging hazırlık kararı

**KÜÇÜK DÜZELTMELERDEN SONRA HAZIR**

Gerekçe — `STAGING TESTİNE HAZIR` için istenen 8 koşulun durumu:

- Runtime error terminal olay olarak işleniyor. ✅ (bölüm 3-4, 7 test)
- 401/403/422 retry edilmiyor. ✅ (bölüm 5-6, 6 test)
- Completion transient retry doğru. ✅ (bölüm 5, 7)
- SIP busy/no_answer/rejected backend'e doğru taşınıyor. ✅ (bölüm 8-10, 7 test)
- Yeni kritik veya yüksek bulgu kalmıyor. ✅ (bölüm 20-21)
- Voice-agent testleri geçiyor. ✅ (107 passed)
- Backend regresyonu geçiyor. ✅ (118 passed)
- Harici servis olmadan doğrulanabilecek bütün kontroller geçiyor. ✅ (ruff/mypy/pytest/docker config, bölüm 14-19)

Sekiz koşulun tamamı karşılanmış görünüyor; ancak `STAGING TESTİNE HAZIR` yerine bir kademe temkinli karar veriyorum çünkü: (a) bu üç düzeltme de yalnız STATİK doğrulama + fake/mock test double'larıyla kanıtlandı — gerçek bir OpenAI Realtime bağlantısının `recoverable` alanını pratikte NASIL kullandığı, gerçek bir SIP trunk'ın 486/480/603 döndürüp döndürmediği, gerçek bir 429 yanıtının `Retry-After` formatı staging'den önce hiç gözlemlenmedi; (b) bu ikinci düzeltme turunun kendisi, birinci turun bağımsız denetimde 3 yeni yüksek bulgu çıkarmasının bir kanıtı — üçüncü bir bağımsız gözün (ilk gerçek staging test sonrası) benzer şekilde faydalı olacağı beklenir. Staging'e geçiş için ek bir düzeltme turu GEREKMİYOR; yalnız ilk gerçek test allowlist'li tek numarayla, sonuçlar dikkatle gözden geçirilerek yapılmalı.

## 24. Git durumu

Repo hâlâ ilk commit öncesi; `git status --short` tüm proje dosyalarını untracked (`??`) gösteriyor — bu, önceki tüm Phase 4 turlarıyla (Codex'in Aşama 1-3'ü, Claude'un ilk Aşama 4'ü, ilk düzeltme turu, bu ikinci düzeltme turu) tutarlı bir durumdur, bu oturumun bir yan etkisi değildir. Commit, push, reset, checkout, clean veya stash yapılmadı. `.env` veya secret dosyası açılmadı/oluşturulmadı. Harici ağ çağrısı (OpenAI/LiveKit/Netgsm) yapılmadı. Gerçek telefon araması yapılmadı. Proje dışı `~/AI_MEMORY/` dosyaları değiştirilmedi.
