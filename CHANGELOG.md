# CHANGELOG.md

## Değişiklik Geçmişi

### 2026-07-18 — Aşama 4, 2. Düzeltme: Codex'in 3 Yüksek Bulgusu (runtime error, completion retry, SIP→status)

**Aşağıdaki "Aşama 4 Düzeltmesi" girdisini tamamlar** — o girdi iki KRİTİK bulguyu kapatmıştı; bağımsız Codex denetimi (`CODEX_AUDIT_PHASE_4_FIX.md`) bunu büyük ölçüde doğruladı ama staging'i engelleyen 3 YÜKSEK risk buldu ve kararı **"ÖNEMLİ DÜZELTMELER GEREKLİ"** olarak verdi. Bu girdi o üç bulguyu kapatır (detay: `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`):

- **Runtime error terminal düzeltildi** — `termination.py::CallTerminationWaiter._on_error()` artık gerçek SDK alanı `ErrorEvent.error.recoverable`'a bakıyor (kaynakta doğrulandı: `LLMError`/`RealtimeModelError`/`STTError`/`TTSError` hepsi bu alanı taşır, OpenAI plugin bağlantı/auth hatalarında `recoverable=False` kullanır). Yalnız KESİN fatal (`recoverable=False`) hatalar terminal sayılır; kurtarılabilir hatalar SDK'nın kendi içinde toparlanmasına bırakılır — job gereksiz yere sonlandırılmaz. Tüm yarışlarda (remote hangup/timeout/end-call ile) ilk gelen terminal sinyal deterministik korunur.
- **Completion retry sınıflandırması düzeltildi** — `agent/api_client.py`'ye `InternalAPIPermanentError` (400/404/422/vb., tek deneme) ve `InternalAPITransientError` (kendi iç retry bütçesi tükenen timeout/connection-reset/5xx, üst katman retry edebilir) eklendi; 429 artık `Retry-After` header'ına (üst sınırla, `HTTP_MAX_RETRY_AFTER_SECONDS`) uyarak sınırlı retry ediyor. `CompletionGuard` artık yalnız `InternalAPITransientError`'ı retry ediyor; 401/403/404/409-conflict/422 ve sınıflandırılamayan tipler İLK denemede fail ediyor.
- **SIP terminal sonucu backend'e taşındı** — Backend `CompletionIn` şemasına opsiyonel `sip_reason` alanı eklendi (geriye dönük uyumlu). `/complete` endpoint'i artık `sip_reason`'a göre call'u doğru terminal statüye (`busy`/`no_answer`/`rejected`/`cancelled`, bilinmeyen nedenler için mevcut `failed` fallback'i korunur) taşıyor. Daha da önemlisi: `/complete`'in campaign_lead güncellemesi, her zaman koşulsuz "completed" yazan eski inline kod yerine artık mevcut `campaign_service.handle_call_terminal()` + `maybe_complete_campaign()`'ı çağırıyor — busy/no_answer/rejected sonuçları artık gerçekten kampanya retry zamanlamasına (`compute_next_retry`, durum bazlı çarpan) yansıyor.
- Doğrulama: voice-agent `107 passed` (1. düzeltmeden sonra 83'tü), coverage `%87` (%86'ydı), Ruff/MyPy temiz. Backend `118 passed` (111'di, 7 yeni SIP-mapping testi eklendi, hiçbiri bozulmadı), Ruff/MyPy temiz. Docker config (`normal` + `voice` profili) geçti.

### 2026-07-18 — Aşama 4 Düzeltmesi: Gerçek Konuşma Döngüsü ve Log Redaksiyonu

**Aşağıdaki 2026-07-18 "Aşama 4" girdisini düzeltir** — o girdi "tamamlandı" diyordu ancak bağımsız denetim (`CLAUDE_AUDIT_PHASE_4.md`) agent'ın hiç konuşma yapmadan (açılış cümlesinden hemen sonra) kapandığını ve log traceback'lerinin PII/secret sızdırdığını kanıtladı. Bu girdi o iki KRİTİK bulguyu ve 4 YÜKSEK bulguyu kapatır (detay: `CLAUDE_FIX_PHASE_4.md`):

- **KRİTİK-1 düzeltildi** — Yeni `agent/termination.py::CallTerminationWaiter`: açılıştan sonra gerçek SDK `close` event'ini (`CloseReason.PARTICIPANT_DISCONNECTED/USER_INITIATED/JOB_SHUTDOWN/ERROR/TASK_COMPLETED`), `end_call_safely` tool'unun tetiklediği kontrollü kapanışı (agent'ın kapanış cümlesini bitirmesi `agent_state_changed` ile beklenir) veya `max_call_duration_seconds` timeout'unu bekler. Job artık gerçek bir terminal olay gelmeden tamamlanmıyor.
- **KRİTİK-2 düzeltildi** — `agent/logging.py`'ye `RedactingFormatter` eklendi: `logger.exception()`/`exc_info=True` ile basılan TAM traceback artık redakte ediliyor (öncekinde yalnız `record.msg`/`record.args` temizleniyordu, traceback'e hiç dokunulmuyordu). Canlı repro ile doğrulandı: telefon + Bearer token artık traceback'te görünmüyor.
- **YÜKSEK-1 düzeltildi** — `CompletionGuard` artık `_completed` bayrağını yalnız `api.complete()` GERÇEKTEN başarılı olduğunda set ediyor; başarısızlıkta 3 denemeye kadar retry, tükenirse açık `logger.error` + `CompletionError` (sessiz yutma yok). `asyncio.Lock` ile eşzamanlı çağrı yarışına karşı korunuyor.
- **YÜKSEK-2 düzeltildi** — `agent/usage.py::usage_from_session()` gerçek `AgentSession.usage.model_usage`'ı okuyor ve job_handler'a bağlandı (eskiden `usage_from_sdk_event()` hiç çağrılmıyordu).
- **YÜKSEK-3 düzeltildi** — `SipCallError.sip_status_code` artık korunuyor; RFC 3261 durum koduna göre busy/no_answer/rejected/cancelled/authentication_error/trunk_error ayrımı yapılıyor (`agent/errors.py::classify_sip_status`).
- **YÜKSEK-4 düzeltildi** — `LiveKitRealtimeSessionAdapter`/`LiveKitSIPParticipantAdapter` artık gerçek sınıflarıyla test ediliyor (ağ çağrısı yapılmadan nesne inşası + SIP request alan doğrulaması).
- Bonus: gerçek `conversation_item_added`/`user_state_changed`/`agent_state_changed` event'leri artık transcript ve speech lifecycle event'lerine bağlandı (`SessionEventBridge`) — eskiden konuşma hiç olmadığı için bu event'ler de hiç üretilmiyordu.
- Doğrulama: voice-agent `83 passed` (eskiden 40), coverage `%86` (eskiden %78), Ruff/MyPy temiz. Backend regresyon değişmedi: `111 passed, 1 warning`, Ruff/MyPy temiz. Docker config (`normal` + `voice` profili) geçti.

### 2026-07-18 — Aşama 4: LiveKit Voice Agent ve OpenAI Realtime Runtime ⚠️ (yukarıdaki girdiyle düzeltildi)

- `services/voice-agent` Python servisi eklendi.
- Typed internal API client, PII-safe logging/redaction ve strict config eklendi.
- LiveKit Agents worker/job runtime, OpenAI Realtime adapter ve LiveKit SIP participant adapter eklendi.
- 12 controlled tool, lifecycle event, transcript, usage ve completion akışları eklendi.
- `docs/voice-agent-runtime.md`, `infrastructure/docker/voice-agent.Dockerfile` ve compose `voice` profili eklendi.
- Doğrulama: voice-agent `40 passed`, coverage `%78`, Ruff/MyPy temiz. Backend regresyon: `111 passed, 1 warning`, Ruff/MyPy temiz.
- **NOT:** Bu girdideki "tamamlandı" iddiası hatalıydı — gerçek konuşma döngüsü eksikti. Bkz. yukarıdaki düzeltme girdisi ve `CLAUDE_AUDIT_PHASE_4.md`.
