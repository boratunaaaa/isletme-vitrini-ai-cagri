# Voice Agent Runtime

> **2026-07-18 güncellemesi (2. tur):** `CODEX_AUDIT_PHASE_4_FIX.md`'nin bağımsız
> denetiminde tespit ettiği üç YÜKSEK bulgu düzeltildi: (1) runtime `error` event'i
> artık `recoverable=False` iken terminal sayılıyor, (2) `CompletionGuard` yalnız
> GERÇEKTEN geçici hataları retry ediyor (401/403/404/409-conflict/422 tek denemede
> fail eder), (3) SIP busy/no_answer/rejected backend call status'una ve kampanya
> retry zamanlamasına taşınıyor. Detay: `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`.
>
> **2026-07-18 güncellemesi (1. tur):** Bu doküman `CLAUDE_AUDIT_PHASE_4.md`'de tespit edilen
> KRİTİK-1 (gerçek konuşma döngüsü eksikti) ve KRİTİK-2 (log redaksiyonu traceback'i
> kapsamıyordu) bulgularının düzeltilmesi sonrası güncellenmiştir. Detay: `CLAUDE_FIX_PHASE_4.md`.

## Runtime mimarisi

`services/voice-agent` ayrı bir Python 3.11 servisidir. LiveKit Agents job runtime içinde çalışır, backend ile yalnız `/api/internal/v1` internal contract üzerinden konuşur. Agent DB'ye, Netgsm credential'larına veya serbest HTTP/SQL yüzeylerine erişmez.

## Job lifecycle (gerçek konuşma döngüsü)

LiveKit job metadata içinde yalnız `call_id` beklenir. Gerçek akış (`agent/job_handler.py::VoiceAgentJobHandler.handle`):

1. Backend `/bootstrap` çağrılır, `agent_job_started` event'i gönderilir.
2. `/dial-plan` alınır, LiveKit odasına bağlanılır (`ctx.connect()`).
3. `agent/termination.py::CallTerminationWaiter` kurulur (henüz beklemeye başlamaz) — `end_call_safely` tool'unun tetikleyeceği sinyali tutacak `asyncio.Event` bu noktada hazırlanır.
4. Kontrollü tool'lar kayıt edilir (`ToolExecutor`, `end_call_safely` başarılı işlendiğinde waiter'ı tetikleyecek callback ile).
5. SIP participant oluşturulur (`wait_until_answered=True` ile bloklayan gerçek LiveKit SIP çağrısı). Başarısız olursa (busy/no_answer/rejected/timeout/...) job burada sonlanır — Realtime session hiç başlatılmaz.
6. Telefon cevaplandıktan SONRA OpenAI Realtime `AgentSession` başlatılır (`agent_session_started` event'i).
7. Açılış cümlesi yalnız bir kez söylenir (`OpeningGate.play_once_after_answer`).
8. **Gerçek görüşme**: `CallTerminationWaiter.wait(session)` çağrılır ve şu yollardan biriyle GERÇEKTEN bitene kadar bekler:
   - SDK'nın `close` event'i (karşı taraf kapattı / job shutdown / görev tamamlandı — `CloseReason`).
   - SDK'nın `error` event'i (`ErrorEvent.error.recoverable`) **kesin fatal** (`recoverable=False`) ise — bkz. "Runtime error terminal" bölümü. `recoverable=True`/bilinmeyen ise terminal SAYILMAZ, SDK kendi içinde toparlanır.
   - Modelin `end_call_safely` tool'unu çağırması → agent'ın kapanış cümlesini bitirmesi (`agent_state_changed` ile izlenir) → kontrollü `session.aclose()`.
   - `max_call_duration_seconds` aşılırsa zorla TIMEOUT.
   - Tüm yarışlarda İLK gelen terminal sinyal deterministik olarak kazanır (`_close_event` yalnız bir kez set edilir).
9. Gerçek kullanım (`session.usage`) okunur, terminal event + completion gönderilir (yalnız BİR kez, retry'lı `CompletionGuard` ile).
10. Kaynaklar temizlenir: event/transcript kuyrukları `stop()` ile (arka plan task'ları iptal edilerek) kapatılır, Realtime session kapatılır, SIP participant/room kaldırılır, `ctx.shutdown()` çağrılır.

Görüşme boyunca gerçek SDK event'leri (`user_state_changed`, `agent_state_changed`, `conversation_item_added`) `agent/job_handler.py::SessionEventBridge` ile backend'e aktarılır: konuşma başlama/bitme event'leri (`user_speech_started/stopped`, `agent_speech_started/stopped`) ve final transcript turn'leri.

## Runtime error terminal (fatal/non-fatal ayrımı)

Gerçek SDK'da (`llm.LLMError`, `llm.RealtimeModelError`, `stt.STTError`, `tts.TTSError`) her hata nesnesi bir `recoverable: bool` alanı taşır (kaynakta doğrulandı: `livekit/agents/llm/realtime.py`, OpenAI plugin `_emit_error(error, recoverable=...)` — bağlantı/auth gibi kurtarılamaz durumlarda `False`, toparlanabilir durumlarda `True`). `CallTerminationWaiter._on_error()`:

- `recoverable is False` → terminal sinyal (`DisconnectReason.OPENAI_FAILURE`), yalnız İLK fatal hata sayılır (sonrakiler `_close_event` zaten set olduğu için yok sayılır).
- `recoverable is True` veya bilinmeyen → terminal DEĞİL; SDK kendi içinde toparlanır, görüşme kesintisiz devam eder.

Bu ayrım olmadan (önceki sürüm) her `error` event'i yalnız kaydediliyordu, hiçbir zaman terminal sayılmıyordu — fatal bir hata sonrası job `max_call_duration_seconds`'a kadar (yanlışlıkla `timeout` nedeniyle) açık kalabiliyordu.

## Bootstrap akışı

`GET /calls/{call_id}/bootstrap` sistem promptu, opening script, kampanya modeli, voice, knowledge base, policy ve güvenli işletme bağlamını döndürür. Tam telefon prompt'a veya loglara eklenmez.

## SIP participant akışı

Dial-plan response içindeki `phone_e164`, `sip_trunk_id`, `room_name` ve participant alanları `CreateSIPParticipantRequest` için kullanılır (`agent/sip.py::build_sip_participant_request` — ağ çağrısı yapmadan test edilebilir saf fonksiyon). SIP secret veya Netgsm credential backend response'undan alınmaz.

SIP başarısızlıkları ayrıştırılıyor: `SipCallError.sip_status_code` korunur ve RFC 3261 standart SIP durum kodlarına göre sınıflandırılır (`agent/errors.py::classify_sip_status`): 486→busy, 480/408→no_answer, 603→rejected, 487→cancelled, 401/403/407→authentication_error, 5xx→trunk_error. Bu sınıflandırma hem `agent_job_failed` event payload'ında (`sip_reason`) HEM DE `/complete` çağrısının `CompletionIn.sip_reason` alanında taşınır — backend bunu call status'una (`busy`/`no_answer`/`rejected`/`cancelled`) ve kampanya retry zamanlamasına (`compute_next_retry`, durum bazlı çarpan: busy 0.5x, rejected 2x) yansıtır (bkz. `docs/internal-voice-agent-api.md#completion`). Önceden bu sınıflandırma yalnız event payload'ında kalıyordu; backend her SIP hatasını `sip_failure`→`FAILED` genel kovasına atıyordu, retry politikası busy/no_answer/rejected ayrımını hiç göremiyordu.

## OpenAI Realtime session

LiveKit `livekit-agents[openai]` plugin'i ile `openai.realtime.RealtimeModel` kullanılır. Kurulu sürümler: LiveKit Agents `1.5.17`, OpenAI plugin `1.5.17`, OpenAI Python `2.46.0`. Model kataloğu `gpt-realtime-2.1-mini` ve `gpt-realtime-2.1`; voice kataloğu backend ile uyumlu sınırlıdır.

Bilinen küçük teknik borç: `AgentSession(allow_interruptions=..., min_interruption_duration=...)` kwargs'ları kurulu SDK sürümünde deprecated (hâlâ çalışıyor, kaldırılmadı) — ileride `turn_handling=TurnHandlingOptions(...)`'a geçiş yapılmalı.

## Tool registration

Session'a yalnız 12 kontrollü tool kaydedilir. Tool çağrıları backend internal endpointlerine gider, `tool_call_started/completed/failed` lifecycle eventleri üretir ve model tarafına ham JSON yerine kısa kontrollü sonuç döner. `end_call_safely` başarıyla işlendiğinde `CallTerminationWaiter.request_end_call()` tetiklenir — bu, görüşmenin kontrollü olarak sonlandırılmasının TEK yoludur (agent kendi kendine `ctx.shutdown()` çağırmaz).

## Transcript

Final transcript turn'leri iki kaynaktan gelir: (a) gerçek `conversation_item_added` SDK event'i (`SessionEventBridge`), (b) bounded async queue ile internal endpoint'e gönderim (`QueuedTranscriptSink`). Partial turnler kalıcı endpoint'e gönderilmez. Lokal ön redaksiyon uygulanır, backend redaksiyonu ana güvenlik katmanı olarak kalır.

## Usage

Görüşme sonunda `AgentSession.usage.model_usage` (gerçek `ModelUsageCollector` çıktısı) okunur (`agent/usage.py::usage_from_session`). SDK alan adları (`input_cached_audio_tokens` vb.) backend şemamızdan (`cached_input_audio_tokens` vb.) farklıdır — bu fonksiyon doğru yönde eşleme yapar, SDK'nın sağlamadığı hiçbir alanı (`reasoning_tokens`) uydurmaz. Session hiç usage sağlamazsa `usage_source=unavailable` raporlanır.

## Completion

`agent/job_handler.py::CompletionGuard` completion'ı tek seferlik VE güvenilir hale getirir: `_completed` bayrağı yalnız `api.complete()` GERÇEKTEN başarılı olduğunda set edilir (öncekinin aksine — eskiden API çağrısından ÖNCE set ediliyordu ve başarısızlık sessizce yutuluyordu). `asyncio.Lock` ile eşzamanlı çağrı yarışlarına karşı korunur (ör. remote hangup ile end_call_safely aynı anda gerçekleşirse).

**Retry sınıflandırması** (`agent/api_client.py` + `agent/errors.py`): `CompletionGuard` yalnız `InternalAPITransientError` için retry eder — bu istisna `api_client.py`'nin kendi iç retry bütçesi (network timeout/connection reset/429 `Retry-After`/5xx) TÜKENDİKTEN SONRA fırlatılır. Kalıcı hatalar İLK denemede fail eder, hiç retry edilmez:

| Durum | Exception | Retry? |
|---|---|---|
| 401/403 | `InternalAPIAuthenticationError` | Hayır |
| 400/404/422/vb. | `InternalAPIPermanentError` | Hayır |
| 409 (idempotent aynı payload) | — (200 döner, hata değil) | — |
| 409 (farklı payload) | `DuplicateConflictError` | Hayır |
| Timeout/connection reset/5xx (kendi iç retry'ı tükenince) | `InternalAPITransientError` | Evet (3 denemeye kadar, backoff'lu) |
| 429 | `_RateLimitedSignal` → `Retry-After` (üst sınır `HTTP_MAX_RETRY_AFTER_SECONDS`, varsayılan 30s) ile `api_client.py` seviyesinde retry, tükenince `InternalAPITransientError` | Evet (sınırlı) |
| Sınıflandırılamayan/bilinmeyen tip | — | Hayır (güvenli varsayılan) |

Tüm geçici denemeler tükenirse (veya ilk denemede kalıcı hata alınırsa) açık `logger.error` (hata sınıfı adı + redakte edilmiş mesajla) + `CompletionError` üretilir — sessiz yutma yok. Aynı `completion_event_id` (`f"completion-{call_id}"`) tüm denemelerde korunur.

Remote hangup, agent hangup (`end_call_safely`), timeout, SIP failure, OpenAI failure ve generic agent error için ayrı disconnect reason değerleri desteklenir (`agent/models.py::DisconnectReason`, gerçek SDK `CloseReason`'dan eşlenir — bkz. `agent/termination.py`).

## Error handling

Typed hata sınıfları `agent/errors.py` içindedir. Log filter + formatter (`agent/logging.py`) token, API key, telefon ve email benzeri hassas değerleri **hem log mesajında hem de `logger.exception()`/`exc_info=True` ile basılan tam traceback'te** redakte eder (`RedactingFormatter`, `formatException`/`formatStack` override'ları dahil). Bu, `tests/test_logging_redaction.py`'de gerçek handler+formatter çıktısı üzerinden regresyon testleriyle korunur.

## Required environment variables

Production runtime için gerekliler:

- `INTERNAL_API_BASE_URL`
- `INTERNAL_SERVICE_TOKEN`
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`
- `OPENAI_API_KEY`

Opsiyonel (varsayılanı var): `END_CALL_GRACE_SECONDS` (varsayılan 8s) — `end_call_safely` sonrası agent'ın kapanış cümlesini bitirmesi için beklenecek üst sınır. `HTTP_MAX_RETRY_AFTER_SECONDS` (varsayılan 30s) — 429 `Retry-After` başlığının kırpılacağı üst sınır.

## Config validation

```bash
cd services/voice-agent
uv run python -m agent.main --check-config
```

Development ortamında bu komut dış bağlantı yapmaz ve eksik runtime credential'ları açıkça listeler. Gerçek worker başlatma credential eksikse fail-fast yapar.

## Development testleri

```bash
uv run ruff check agent tests
uv run mypy agent
uv run pytest -q
uv run pytest --cov=agent --cov-report=term-missing
```

Güncel sonuç (2026-07-18, 2. düzeltme turu sonrası): `107 passed`, coverage `%87`. Önemli test dosyaları:

- `tests/test_termination.py` (16 test) — `CallTerminationWaiter`'ın close-event eşlemesi, fatal/recoverable `error` event ayrımı, end_call grace akışı, timeout, tüm terminal-sinyal yarışları (remote hangup/end-call/fatal-error/timeout arasında ilk-gelen-kazanır).
- `tests/test_completion_guard.py` (12 test) — permanent (401/403/404/422/409-conflict, tek deneme) vs transient (3 denemeye kadar) retry sınıflandırması, tükenme, eşzamanlı çağrı yarışı (`asyncio.Lock`), completion event ID stabilitesi.
- `tests/test_api_client.py` (14 test) — 429/`Retry-After` (üst sınır dahil), permanent 4xx tek deneme, 5xx/timeout exhaustion → `InternalAPITransientError`.
- `tests/test_logging_redaction.py` — gerçek handler+formatter çıktısı üzerinden traceback redaksiyonu.
- `tests/test_job_handler.py` (14 test) — job'ın açılıştan sonra AKTİF kaldığını, yalnız gerçek terminal event'lerle (remote hangup, end-call, timeout, fatal/recoverable runtime error, SIP hata ayrımı) tamamlandığını kanıtlayan lifecycle testleri.
- `tests/test_runtime_adapters.py` — gerçek `LiveKitRealtimeSessionAdapter`/`LiveKitSIPParticipantAdapter`'ın (ağ çağrısı olmadan) doğru SDK nesneleri/protobuf alanları ürettiği.

Backend tarafında (`services/api`) yeni SIP-mapping testleri: `tests/integration/test_internal_voice_agent_api.py` içine busy/no_answer/rejected/timeout/unknown-reason/backward-compat senaryoları eklendi (118 backend testi toplam, önceki 111'i bozmadan).

## Staging hazırlığı

Staging öncesi LiveKit URL/API key/secret, OpenAI API key, önceden oluşturulmuş LiveKit SIP outbound trunk ID ve backend internal token tanımlanmalı. İlk gerçek testte yalnız allowlist test numarası kullanılmalı.

## Bu aşamada yapılmayanlar

Gerçek OpenAI isteği, LiveKit Cloud bağlantısı, Netgsm bağlantısı, SIP trunk oluşturma, gerçek telefon araması, frontend geliştirme, production deployment, commit ve push yapılmadı (ilk Aşama 4'te de, bu düzeltme oturumunda da).
