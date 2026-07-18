# CODEX_AUDIT_PHASE_4_FIX.md

## 1. Yönetici özeti

Karar: **ÖNEMLİ DÜZELTMELER GEREKLİ**.

Claude'un iki kritik düzeltmesi bağımsız incelemede büyük ölçüde doğrulandı:

- Açılıştan hemen sonra completion gönderme bug'ı kapanmış. `VoiceAgentJobHandler.handle()` artık açılış sonrası `CallTerminationWaiter.wait()` ile terminal olayı bekliyor (`services/voice-agent/agent/job_handler.py:350-376`).
- Traceback redaksiyonu kapanmış. `RedactingFormatter` nihai formatter çıktısını ve exception/stack metnini redakte ediyor (`services/voice-agent/agent/logging.py:35-46`) ve testler gerçek handler çıktısını assert ediyor (`services/voice-agent/tests/test_logging_redaction.py:39-145`).

Ancak staging testine doğrudan geçmek için üç yüksek risk kaldı:

- Runtime `error` event'i terminal sayılmıyor; `CallTerminationWaiter._on_error()` yalnız kaydediyor, `_close_event` set etmiyor (`services/voice-agent/agent/termination.py:143-147`).
- `CompletionGuard` permanent internal API hatalarını da retry ediyor; `401/403/422` sınıflandırması completion katmanında korunmuyor (`services/voice-agent/agent/job_handler.py:237-247`).
- SIP nedeni sınıflandırılıyor ama backend terminal status/outcome'a taşınmıyor; `busy/no_answer/rejected` hâlâ completion tarafında `sip_failure` ve backend fallback'te technical failure'a düşebilir (`services/voice-agent/agent/job_handler.py:333-344`, `services/api/app/api/routes/internal/calls.py:478-491`).

Doğrulamalar geçti: voice-agent 83 test, coverage %86, Ruff, MyPy; backend 111 test, Ruff, MyPy; Docker compose config normal ve `voice` profile.

## 2. Denetlenen kapsam

Okunan ana kaynaklar:

- `CLAUDE_AUDIT_PHASE_4.md`
- `CLAUDE_FIX_PHASE_4.md`
- `CLAUDE_PROGRESS_PHASE_4.md`
- `CODEX_PROGRESS_PHASE_3.md`
- `docs/internal-voice-agent-api.md`
- `docs/voice-agent-runtime.md`
- `services/voice-agent/pyproject.toml`
- `services/voice-agent/uv.lock`
- `services/voice-agent/agent/**`
- `services/voice-agent/tests/**`
- `docker-compose.dev.yml`
- `infrastructure/docker/voice-agent.Dockerfile`
- `PROJECT_STATUS.md`
- `TODO.md`
- `CHANGELOG.md`
- `~/AI_MEMORY/GLOBAL_MEMORY.md`
- `~/AI_MEMORY/GLOBAL_STATUS.md`
- `~/AI_MEMORY/GLOBAL_TODO.md`

Kod değişikliği yapılmadı. Test, format, lock, migration, Docker servis başlatma, OpenAI/LiveKit/SIP/Netgsm çağrısı yapılmadı.

## 3. Git ve dosya durumu

Komut sonuçları:

```text
pwd
/Users/kadirugur/Projects/isletme-vitrini-ai-cagri

git status --short
?? .env.example
?? .gitignore
?? .prettierrc
?? AGENTS.md
?? CHANGELOG.md
?? CLAUDE.md
?? CLAUDE_AUDIT_PHASE_4.md
?? CLAUDE_FIX_PHASE_4.md
?? CLAUDE_PROGRESS_PHASE_4.md
?? CODEX_AUDIT.md
?? CODEX_PROGRESS_PHASE_1.md
?? CODEX_PROGRESS_PHASE_2.md
?? CODEX_PROGRESS_PHASE_3.md
?? DECISIONS.md
?? IMPLEMENTATION_PLAN.md
?? Makefile
?? PROJECT_STATUS.md
?? PROMPTS.md
?? TODO.md
?? docker-compose.dev.yml
?? docs/
?? infrastructure/
?? package.json
?? pnpm-workspace.yaml
?? services/
?? turbo.json

git diff --stat
(boş)

git diff --name-only
(boş)

git log --oneline -5 2>/dev/null || true
(boş)
```

Repo hâlâ tamamen untracked durumda. Bu nedenle Claude'un değiştirdiği dosyalar git diff ile bağımsız çıkarılamıyor; `CLAUDE_FIX_PHASE_4.md:134-164` raporuna ve dosya içeriklerine göre değişiklikler `services/voice-agent/agent/**`, ilgili testler, status/doküman dosyaları ve önceki Phase 4 raporları üzerinde. Bu denetimde beklenmeyen cache/log/ses/transkript/secret/model dosyası git status'a eklenmedi.

Proje dışı durum: `~/AI_MEMORY/GLOBAL_STATUS.md` hâlâ eski "Aşama 4 tamamlandı, 40 test, %78 coverage" bilgisini taşıyor. Bu dosya talimat gereği değiştirilmedi; manuel güncelleme gerekiyor.

## 4. Önceki kritik/yüksek bulguların kapanış matrisi

| Bulgu | Karar | Dosya/satır | Kanıt | Etki | Kalan risk |
|---|---|---:|---|---|---|
| 1. Açılıştan hemen sonra job'ın tamamlanması | TAM OLARAK KAPATILDI | `job_handler.py:350-376`, `test_job_handler.py:129-175` | Açılış sonrası `waiter.wait()` bekleniyor; test completion'ın remote hangup öncesi boş kaldığını doğruluyor. | Job artık açılış sonrası kapanmıyor. | Gerçek staging konuşması hâlâ credential gerektiriyor. |
| 2. Gerçek konuşma/dinleme döngüsünün olmaması | KISMEN KAPATILDI | `job_handler.py:350-359`, `session.py:133-149`, `termination.py:99-130` | Realtime session start ediliyor ve SDK close/end-call/timeout bekleniyor. | Üretim akışında aktif bekleme var. | Runtime `error` event'i tek başına terminal değil. |
| 3. Hatalı testin bug'ı başarı kabul etmesi | TAM OLARAK KAPATILDI | `test_job_handler.py:129-175` | Yeni test `task.done() is False`, completion yok ve terminal olay sonrası tek completion bekliyor. | Eski false-positive davranış kaldırılmış. | Test gerçek kullanıcı turnünden model cevabını aynı testte kanıtlamıyor. |
| 4. Traceback içinde telefon/Bearer sızıntısı | TAM OLARAK KAPATILDI | `logging.py:35-46`, `redaction.py:33-45`, `test_logging_redaction.py:39-145` | Formatter nihai log çıktısını redakte ediyor; telefon, Bearer, httpx, transcript exception testleri var. | PII/secret traceback sızıntısı kapandı. | Üçüncü taraf non-root handler sonradan eklenirse ayrıca konfigüre edilmeli. |
| 5. Completion başarısızlığının sessizce yutulması | TAM OLARAK KAPATILDI | `job_handler.py:218-256`, `test_completion_guard.py:72-107` | `_completed` yalnız başarıdan sonra set ediliyor; tükenince `CompletionError` fırlıyor. | Sessiz kayıp yok. | Yeni retry sınıflandırması yüksek bulgu. |
| 6. Usage tracking'in runtime'a bağlı olmaması | TAM OLARAK KAPATILDI | `job_handler.py:362-364`, `usage.py:64-98`, `test_transcript_usage.py:50-80` | Final `session.usage.model_usage` okunuyor; SDK alanları doğru eşleniyor. | Gerçek provider-reported final usage backend'e gider. | Incremental usage yok; SDK kaynakta emit noktası doğrulanmadığı için kabul edilebilir sınırlama. |
| 7. SIP hata nedenlerinin ayrıştırılmaması | KISMEN KAPATILDI | `errors.py:41-63`, `sip.py:82-93`, `job_handler.py:333-344` | RFC 3261 status code sınıflandırması var ve event payload'ına `sip_reason` ekleniyor. | Log/event düzeyinde busy/no_answer/rejected ayrılıyor. | Backend status/outcome hâlâ bu nedeni kullanmıyor. |
| 8. Production adapterların gerçek SDK sınıflarıyla test edilmemesi | TAM OLARAK KAPATILDI | `test_runtime_adapters.py:129-245` | Gerçek `AgentSession`, `Agent`, `openai.realtime.RealtimeModel`, `CreateSIPParticipantRequest`, `AgentServer` instantiate ediliyor. | Constructor/signature hataları yakalanır. | Event adı ve gerçek network lifecycle staging'de doğrulanacak. |

## 5. Gerçek konuşma lifecycle

Üretim akışı:

1. LiveKit job entrypoint `AgentServer.rtc_session` ile kuruluyor (`job_handler.py:444-465`).
2. Metadata yalnız `call_id` olarak parse ediliyor (`job_handler.py:259-264`).
3. Bootstrap çağrılıyor (`job_handler.py:300-306`).
4. Dial plan alınıyor (`job_handler.py:307`).
5. Room'a bağlanılıyor (`job_handler.py:308`).
6. SIP participant oluşturuluyor (`job_handler.py:329-346`, `sip.py:67-113`).
7. `wait_until_answered=True` request alanı kullanılıyor (`sip.py:50-58`), sonra `ANSWERED` event gönderiliyor (`job_handler.py:347-349`).
8. `AgentSession.start()` gerçek SDK çağrısı yapılıyor (`session.py:133-149`).
9. Açılış bir kez üretiliyor (`session.py:57-67`, `job_handler.py:353`).
10. Kullanıcı/model konuşma eventleri `SessionEventBridge` ile dinleniyor (`job_handler.py:108-175`).
11. Tool'lar gerçek LiveKit `function_tool` ile kayıtlı (`tools.py:225-327`).
12. Transcript final conversation item üzerinden kuyruğa alınıyor (`job_handler.py:149-175`).
13. Usage görüşme sonunda `session.usage` snapshot'ından alınıyor (`job_handler.py:434-441`).
14. Remote hangup `CloseReason.PARTICIPANT_DISCONNECTED` ile terminal oluyor (`termination.py:44-50`, `99-130`).
15. Agent hangup `end_call_safely` callback'iyle başlıyor (`tools.py:190-192`, `termination.py:149-162`).
16. Timeout `max_call_duration_seconds` ile uygulanıyor (`termination.py:106-119`).
17. Completion bir kez gönderiliyor (`job_handler.py:370-376`, `CompletionGuard`).
18. Queue flush ve cleanup finally bloğunda yapılıyor (`job_handler.py:415-429`).

Olumlu: Açılış sonrası job gerçekten aktif kalıyor; bu mekanizma fake sleep'e değil, SDK event isimlerine (`close`, `agent_state_changed`, `conversation_item_added`) bağlı. Yerel SDK introspection ile `AgentSession.on` event literal listesinde bu isimler doğrulandı.

Eksik: `error` event'i SDK yüzeyinde var; ancak waiter bunu terminal yapmıyor. Terminal close gelmezse job max duration'a kadar bekler ve gerçek hata `timeout` gibi raporlanabilir.

## 6. CallTerminationWaiter

Kanıt:

- Tek close nedenini ilk `close` event koruyor (`termination.py:137-142`).
- `asyncio.Event` ve `asyncio.wait(... FIRST_COMPLETED ...)` kullanılıyor (`termination.py:99-119`).
- Timeout deterministic ve üst sınırlı (`termination.py:106-119`).
- Listener detach var (`termination.py:131-135`).
- Pending waiter task'ları cancel edilip await ediliyor (`termination.py:111-116`).

Risk:

- `_on_error()` yalnız `last_error` kaydediyor, `_close_event` set etmiyor (`termination.py:143-147`). Kod yorumunda "her zaman close event'i tetiklemeyebilir" denmesine rağmen bu durum terminal kabul edilmiyor.
- Waiter tekrar kullanılabilir bir nesne değil; eventler set kalır. Job başına tek kullanımda sorun değil.
- End-call akışı grace penceresini tool callback'inden hemen sonra başlatıyor; modelin kapanış cümlesi geç başlarsa `END_CALL_GRACE_SECONDS` bitip session kapanabilir (`termination.py:149-183`).

Sonuç deterministik mi? Close/end-call/timeout yarışlarında ilk tamamlanan event kazanıyor. Remote hangup + end-call yarışı test edilmiş (`tests/test_termination.py:108-123`). Runtime error + timeout yarışı test edilmemiş ve error tek başına terminal değil.

## 7. Açılış sonrası aktif görüşme

`test_job_stays_active_after_opening_until_real_termination` güçlü bir regresyon testi:

- Açılış bir kez söyleniyor (`test_job_handler.py:148-150`).
- Açılış sonrası completion yok (`test_job_handler.py:151`).
- Job task pending (`test_job_handler.py:152`).
- Terminal olay gelene kadar tamamlanmıyor (`test_job_handler.py:154-159`).
- Remote hangup sonrası tek completion var (`test_job_handler.py:160-165`).

Kalan test boşluğu:

- Aynı testte gerçek kullanıcı turnünün modele girip model cevabı üretmesi kanıtlanmıyor. `simulate_agent_speaking()` adı da yorumdaki "kullanıcı konuşuyor" ifadesiyle tutarsız (`test_job_handler.py:154-156`).
- Tool yolu ayrı test ediliyor (`test_tools.py:47-150`) ve gerçek registry test ediliyor (`test_runtime_adapters.py:178-195`), fakat tam job lifecycle içinde model tool call'ı simüle edilmiyor.

Bu boşluk kritik bulguyu yeniden açmıyor, ama staging öncesi test kalitesi riski olarak kalıyor.

## 8. End-call kontrollü kapanış

Doğrulananlar:

- `end_call_safely` backend tool endpointine gider (`tools.py:166-192`, `test_tools.py:94-131`).
- Backend başarılıysa callback tetiklenir (`tools.py:190-192`).
- Başarısız backend call'da callback tetiklenmez (`test_tools.py:113-131`).
- End-call dışındaki tool'lar kapanışı tetiklemez (`test_tools.py:134-150`).
- Waiter agent state speaking -> idle eventini bekleyebiliyor (`termination.py:164-186`, `test_job_handler.py:207-234`).
- Completion agent hangup olarak gönderiliyor (`test_job_handler.py:232-234`).

Kalan risk:

- Ses çıkışının bitişi doğrudan `SpeechHandle` üzerinden beklenmiyor; state event + grace penceresi var (`termination.py:164-183`).
- Callback tool sonucu modele dönmeden hemen tetiklendiği için kapanış grace süresi, model kapanış cümlesine başlamadan akmaya başlayabilir.
- Remote hangup sırasında end-call beklemesi remote hangup'ı ezmiyor; bu test var (`test_termination.py:108-123`).

## 9. Completion coordinator

Olumlu:

- `asyncio.Lock` tüm `complete_once()` gövdesini koruyor (`job_handler.py:218-256`).
- `_completed` yalnız `api.complete()` başarılı olduktan sonra set ediliyor (`job_handler.py:239-242`).
- Completion event ID stabil: `completion-{call_id}` (`job_handler.py:229-235`).
- Concurrent completion testinde tek API call doğrulanıyor (`test_completion_guard.py:110-130`).
- Tüm retry tükenirse log ve `CompletionError` var (`job_handler.py:248-256`).

Yüksek risk:

- `except Exception` tüm hataları retry ediyor (`job_handler.py:243-247`). Bu, `InternalAPIAuthenticationError` ve `InternalAPIContractError` gibi kalıcı 401/403/422 sınıflarını completion katmanında tekrar kontrolsüz retry'a sokar.
- Testlerde permanent hata sınıfları yok; yalnız transient `RuntimeError` ve always-fail senaryosu var (`test_completion_guard.py:59-107`).

## 10. Usage tracking

SDK doğrulaması:

- `livekit-agents==1.5.17`
- `livekit-plugins-openai==1.5.17`
- `livekit-api==1.2.0`
- `openai==2.46.0`
- `AgentSession.usage` property gerçek ve `AgentSessionUsage(model_usage=...)` döndürüyor.
- `LLMModelUsage` gerçek alanları: `input_audio_tokens`, `input_cached_audio_tokens`, `output_audio_tokens`, `input_text_tokens`, `input_cached_text_tokens`, `output_text_tokens`.

Kod uyumu:

- `usage_from_session()` bu alanları backend schema alanlarına doğru eşliyor (`usage.py:84-98`).
- SDK'da olmayan `reasoning_tokens` uydurulmuyor (`usage.py:94`).
- Usage yoksa `unavailable` gönderiliyor (`usage.py:49-61`, `job_handler.py:437-441`).

Kalan risk:

- Usage gönderimi başarısız olursa `_report_final_usage()` exception fırlatır ve job genel `agent_error` yoluna düşebilir (`job_handler.py:362-376`, `401-414`). Görüşme zaten bitmiş olsa da completion nedeni bozulabilir.
- `ProviderUsageSink` event ID'yi API başarıdan önce `_sent_ids` içine ekliyor (`usage.py:43-47`); aynı nesnede retry edilirse gönderim atlanır.

## 11. SIP hata eşlemesi

Olumlu:

- `486 -> busy`, `480/408 -> no_answer`, `603 -> rejected`, `401/403/407 -> authentication_error`, `5xx -> trunk_error` eşlemesi var (`errors.py:41-63`).
- `SipCallError.sip_status_code` ve `sip_status` korunuyor (`sip.py:82-91`).
- Job event payload'ında `sip_reason` gönderiliyor (`job_handler.py:333-338`).
- SIP request gerçek `CreateSIPParticipantRequest` objesine yazılıyor (`sip.py:41-59`, `test_runtime_adapters.py:198-224`).

Yüksek risk:

- Completion hâlâ her SIP hatasında `DisconnectReason.SIP_FAILURE` gönderiyor (`job_handler.py:339-344`).
- Backend lifecycle event transition map yalnız `dialing/ringing/answered/agent_session_started` eventlerini status'a çeviriyor (`services/api/app/api/routes/internal/calls.py:72-77`).
- Backend complete route invalid transition olursa call status'ü `failed` yapıyor ve fallback outcome `technical_failure` olabilir (`services/api/app/api/routes/internal/calls.py:478-491`, `services/api/app/services/call_service.py:127-168`).

Bu nedenle busy/no_answer/rejected satış tekrar politikası için gereken terminal status ayrımı tamamlanmış değil.

## 12. Logger traceback redaksiyonu

Doğrulananlar:

- `RedactingFormatter.format()` nihai string'i redakte ediyor (`logging.py:38-40`).
- `formatException()` ve `formatStack()` override edilmiş (`logging.py:42-46`).
- `configure_logging()` mevcut handler'lara formatter'ı zorluyor (`logging.py:49-63`).
- `safe_value()` nested mapping/sequence ve bilinmeyen tipleri fail-safe redakte ediyor (`redaction.py:48-73`).
- Testler final handler output seviyesinde telefon, Bearer, OpenAI key, URL query token, httpx exception ve transcript exception redaksiyonunu assert ediyor (`test_logging_redaction.py:39-145`).

Kalan düşük risk:

- Sonradan root dışı logger'a kendi non-redacting handler'ını ekleyen üçüncü taraf kod bu formatter'ı otomatik almayabilir. Mevcut entrypoint için risk kapalı.

## 13. Production adapter testleri

Olumlu:

- Gerçek `AgentSession`, `Agent`, `openai.realtime.RealtimeModel` instantiate ediliyor (`test_runtime_adapters.py:129-149`).
- Model/voice allowlist production adapter üzerinden test ediliyor (`test_runtime_adapters.py:152-175`).
- Runtime session tools listesi gerçek `function_tool` nesnelerinden okunuyor (`test_runtime_adapters.py:178-195`).
- Gerçek SIP protobuf request alanları assert ediliyor (`test_runtime_adapters.py:198-224`).
- `AgentServer` gerçek sınıf olarak inşa ediliyor, worker başlatılmıyor (`test_runtime_adapters.py:233-245`).

Sınırlar:

- Gerçek `.start()` ve LiveKit room lifecycle test edilmiyor; bu yasaklı dış bağlantı gerektiriyor.
- Event adları local SDK type/source introspection ile doğrulandı, ancak testler SDK event registry değişirse doğrudan kırılacak seviyede değil.

## 14. Internal API contract uyumu

Client tarafı:

- Bearer token ve request ID ekleniyor (`api_client.py:155-159`).
- 401/403 client seviyesinde retry edilmiyor (`api_client.py:171-178`, `test_api_client.py:48-72`).
- 503 sınırlı retry ediliyor (`api_client.py:166-170`, `test_api_client.py:75-103`).
- Duplicate conflict ayrılıyor (`api_client.py:190-196`, `test_api_client.py:108-130`).

Contract riski:

- Completion coordinator permanent client hatalarını yeniden retry ediyor; client sınıflandırması üst katmanda kayboluyor.
- SIP failure contract'ı `disconnect_reason` serbest string kabul ediyor, ama backend state/outcome ayrımı `sip_reason` payload'ına bağlı değil.

Backend contract'ında bu denetimde değişiklik yapılmadı.

## 15. Tool runtime bağlantısı

12 kontrollü tool birebir mevcut (`tools.py:21-135`):

- `get_service_information`
- `get_package_information`
- `request_demo_link`
- `schedule_callback`
- `mark_interested`
- `mark_not_interested`
- `mark_wrong_number`
- `mark_decision_maker_unavailable`
- `add_to_suppression_list`
- `request_human_transfer`
- `finalize_call_outcome`
- `end_call_safely`

Kanıt:

- Her tool backend path'e gidiyor ve started/completed event üretiyor (`test_tools.py:47-63`).
- Failure event'i var ve başarısızlık başarılı gibi sunulmuyor (`test_tools.py:66-79`).
- Ham JSON kullanıcıya döndürülmüyor (`test_tools.py:82-88`).
- `end_call_safely` dışındaki tool'lar kapanışı tetiklemiyor (`test_tools.py:134-150`).
- Gerçek AgentSession tools listesinde 12 isim kayıtlı (`test_runtime_adapters.py:178-195`).

Kalan risk:

- Stable `tool_call_id` sadece proses içi counter'a bağlı (`tools.py:160-168`). Aynı model tool retry callback'i aynı backend idempotency ID ile tekrar üretmez. Test "stable" yerine prefix kontrolü yapıyor.

## 16. Transcript ve event queue'ları

Olumlu:

- Event ve transcript consumer task'ları job başında başlıyor (`job_handler.py:282-294`).
- Session event bridge background task referanslarını tutuyor (`job_handler.py:127-131`).
- Final transcript turn gönderiliyor; partial turn sink seviyesinde yok sayılıyor (`transcript.py:44-70`).
- `conversation_item_added` ile transcript aktarımı test edilmiş (`test_job_handler.py:390-430`).
- Queue full sınırsız memory büyütmüyor; düşük öncelikli turn/event drop logu var (`events.py:65-68`, `transcript.py:67-70`).

Kalan risk:

- `events.stop()` ve `transcript.stop()` `queue.join()` için explicit graceful shutdown timeout kullanmıyor (`events.py:70-78`, `transcript.py:72-80`).
- `SessionEventBridge.drain()` 5 saniye bekliyor ama kalan pending task'ları cancel etmiyor (`job_handler.py:121-125`).
- Important eventler queue'ya girmeden direkt API çağrısı yapıyor; delivery failure critical path'i durdurabilir.

## 17. Async/concurrency

Güçlü taraflar:

- Completion lock var.
- Waiter pending task cancel/await ediyor.
- Remote hangup + end-call yarışı test edilmiş.
- Concurrent completion test edilmiş.

Eksikler:

- Runtime `error` event'i terminal değil.
- Worker cancellation path için doğrudan test yok.
- Usage failure + completion reason yarışı test edilmemiş.
- Queue shutdown timeout uygulanmıyor.

## 18. Kaynak temizliği

Doğrulanan cleanup:

- Internal API client `build_server()` finally içinde kapanıyor (`job_handler.py:453-465`).
- Realtime session finally'de kapanıyor (`job_handler.py:422-423`, `session.py:155-156`).
- SIP hangup finally'de çağrılıyor (`job_handler.py:424-428`).
- Transcript/event dispatcher stop ediliyor (`job_handler.py:419-421`).
- Context shutdown var (`job_handler.py:429`).
- Listener detach var (`job_handler.py:416-418`, `termination.py:131-135`).

Kalan risk:

- `realtime.close(runtime)` SIP create öncesi build edilmiş ama hiç start edilmemiş session için de çağrılıyor; Claude raporunda SDK no-op guard doğrulandığı yazılmış, bu denetimde constructor/`aclose` imzası doğrulandı.
- Cleanup sırasında event emit (`AGENT_SESSION_ENDED`) her durumda yapılıyor; session hiç başlamamış hata yollarında semantik olarak yanıltıcı olabilir.

## 19. Docker ve config

Dockerfile:

- Multi-stage yapı var (`infrastructure/docker/voice-agent.Dockerfile:1-16`).
- Non-root `voiceagent` kullanılıyor (`voice-agent.Dockerfile:24-29`).
- Healthcheck `python -m agent.main --check-config` (`voice-agent.Dockerfile:30-31`).
- Secret bake edilmiyor.

Compose:

- Varsayılan compose yalnız Postgres/Redis içeriyor.
- `voice-agent` sadece `profiles: ["voice"]` altında (`docker-compose.dev.yml:73-99`).
- Voice profile command gerçek worker yerine `--check-config` çalıştırıyor (`docker-compose.dev.yml:98`).

Config validation:

```text
uv run python -m agent.main --check-config
configuration valid for dry check; runtime credentials missing: INTERNAL_SERVICE_TOKEN, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_SIP_OUTBOUND_TRUNK_ID, OPENAI_API_KEY
```

## 20. Test kalitesi

Dağılım:

- API client: 6 test.
- Completion guard: 5 test.
- Config: 6 test.
- Job handler: 12 test.
- Logging redaction: 8 test.
- Runtime adapters: 13 test.
- Termination: 9 test.
- Tools: 17 test.
- Transcript/usage: 7 test.

Güçlü alanlar:

- Lifecycle regression testleri var.
- Race-condition için remote hangup + end-call ve concurrent completion var.
- Logging redaction final handler output seviyesinde test ediliyor.
- Production SDK adapter construction gerçek sınıflarla test ediliyor.
- Tool listesi ve backend path'ler tam.
- Usage final snapshot alan eşlemesi testli.
- SIP mapping dolaylı job testleriyle var.

Mock ağırlıklı kalan alanlar:

- Full spoken conversation lifecycle gerçek LiveKit/OpenAI room olmadan fake session ile sınırlı.
- Runtime `error` event terminal davranışı test edilmemiş.
- Permanent completion hataları test edilmemiş.
- Queue shutdown/deadlock senaryoları sınırlı.
- `agent/main.py` otomatik test coverage 0%.

## 21. Status ve dokümantasyon

Olumlu:

- `PROJECT_STATUS.md` eski "Aşama 4 tamamlandı" iddiasını çizip düzeltme notu eklemiş (`PROJECT_STATUS.md:10-29`).
- `CHANGELOG.md` eski hatalı girdiyi uyarıyla tarihsel olarak bırakmış, düzeltme girdisi eklemiş (`CHANGELOG.md:5-26`).
- `CLAUDE_PROGRESS_PHASE_4.md` üstte eski tamamlandı iddiasının hatalı olduğunu söylüyor.
- `docs/voice-agent-runtime.md` gerçek credential ile test yapılmadığını belirtiyor.

Eksik:

- `~/AI_MEMORY/GLOBAL_STATUS.md` hâlâ eski 40 test/%78 coverage ve "tamamlandı" bilgisini taşıyor. Manuel güncelleme gerekiyor.

## 22. Yeni kritik bulgular

Yeni **KRİTİK** bulgu yok.

Önceki iki kritik bulgu staging öncesi tekrar doğrulanması gereken alanlar bıraksa da aynı kritik seviyede açık değil.

## 23. Yeni yüksek bulgular

### YÜKSEK-1 — Runtime `error` event'i terminal kabul edilmiyor

- Dosya/satır: `services/voice-agent/agent/termination.py:99-130`, `143-147`
- Sorun: `AgentSession.on("error")` gerçek SDK event yüzeyinde var, ancak `_on_error()` yalnız `last_error` kaydediyor ve `_close_event` set etmiyor.
- Kanıt: SDK introspection `AgentSession.on` literal listesinde `error` eventini gösterdi. Kod yorumu "Realtime hatası her zaman close event'i tetiklemeyebilir" diyor, fakat yine de terminal sinyali üretmiyor.
- Gerçek etkisi: Fatal realtime error close event üretmezse job max call duration'a kadar açık kalır, hata `timeout` gibi completion'a yansıyabilir.
- Staging'i engeller mi: Evet.
- Önerilen düzeltme: `error` event'i fatal ise `DisconnectReason.OPENAI_FAILURE` terminal sonucu üretsin veya SDK'da error sonrası close garantisi kaynak/test ile kanıtlansın. `session.emit("error")` no-close testi eklenmeli.
- En uygun uygulayıcı: Claude Sonnet veya Codex.

### YÜKSEK-2 — Completion retry permanent hataları da tekrar deniyor

- Dosya/satır: `services/voice-agent/agent/job_handler.py:237-247`
- Sorun: CompletionGuard tüm exception'ları retry ediyor.
- Kanıt: `except Exception as exc` ve yorumda "her hata retry'a girer" yazıyor. Internal API client 401/403/4xx için typed exception üretse bile üst katman bunu ayırt etmiyor.
- Gerçek etkisi: Yanlış token veya schema bug'ında 3 kez gereksiz `/complete` denenir; shutdown gecikir, log gürültüsü ve backend yükü oluşur.
- Staging'i engeller mi: Evet.
- Önerilen düzeltme: `InternalAPIAuthenticationError`, `InternalAPIContractError`, `DuplicateConflictError` gibi permanent hatalarda retry yapmadan fail et; yalnız timeout/transport/5xx sınıfı transient hataları retry et.
- En uygun uygulayıcı: Codex.

### YÜKSEK-3 — SIP busy/no_answer/rejected backend sonucuna taşınmıyor

- Dosya/satır: `services/voice-agent/agent/job_handler.py:333-344`, `services/api/app/api/routes/internal/calls.py:72-77`, `478-491`, `services/api/app/services/call_service.py:127-168`
- Sorun: SIP reason event payload'ında var, fakat backend call status/outcome buna göre `busy/no_answer/rejected` olmuyor.
- Kanıt: Voice-agent completion nedeni her SIP hata için `sip_failure`; backend transition map `agent_job_failed` payload'ını status'a çevirmiyor. Complete route invalid transition'da `failed` yapıyor ve fallback outcome technical failure'a düşebilir.
- Gerçek etkisi: Satış tekrar politikası için önemli meşgul/cevapsız/reddedildi ayrımı kaybolur.
- Staging'i engeller mi: Evet; özellikle SIP smoke test sonucu değerlendirme yanlış olur.
- Önerilen düzeltme: Minimum backend contract değişikliğiyle SIP terminal reason'ı status/outcome'a map et veya voice-agent ilgili terminal lifecycle event/status endpointini contract'a uygun şekilde kullansın. 486 -> BUSY, 480/408/timeouts -> NO_ANSWER, 603 -> REJECTED, auth/trunk/5xx -> FAILED.
- En uygun uygulayıcı: Codex + backend contract onayı.

## 24. Orta ve düşük bulgular

### ORTA-1 — End-call kapanış cümlesi doğrudan SpeechHandle ile beklenmiyor

- Dosya/satır: `services/voice-agent/agent/termination.py:149-183`, `services/voice-agent/agent/session.py:62-67`
- Sorun: Tool callback kapanış sinyalini model tool result'ını aldıktan hemen sonra değil, backend call tamamlanınca başlatıyor; bekleme `agent_state_changed` + grace ile sınırlı.
- Etki: Modelin kapanış cümlesi geç başlarsa session kapanabilir.
- Öneri: `generate_reply`/speech handle veya SDK speech completion event'iyle daha kesin bekleme tasarla.

### ORTA-2 — Usage delivery failure terminal reason'ı bozabilir

- Dosya/satır: `services/voice-agent/agent/job_handler.py:362-376`, `434-441`, `services/voice-agent/agent/usage.py:43-47`
- Sorun: Usage send exception'ı normal terminal flow'dan generic exception'a düşebilir; `_sent_ids` başarıdan önce set ediliyor.
- Etki: Remote hangup sonrası completion `agent_error` olabilir veya retry atlanabilir.
- Öneri: Usage failure'ı logla/`unavailable` veya best-effort olarak işaretle; completion reason'ı bozma.

### ORTA-3 — Queue stop için explicit graceful timeout yok

- Dosya/satır: `services/voice-agent/agent/events.py:70-78`, `services/voice-agent/agent/transcript.py:72-80`
- Sorun: `queue.join()` timeout'suz.
- Etki: API client veya consumer wedged olursa shutdown uzayabilir.
- Öneri: `GRACEFUL_SHUTDOWN_SECONDS` ile bounded drain uygula.

### DÜŞÜK-1 — `agent/main.py` otomatik test coverage 0%

- Dosya/satır: coverage raporu `agent/main.py 0%`
- Etki: CLI wrapper regresyonu sadece manuel `--check-config` ile yakalanır.
- Öneri: Unit test ile `_check_config()` ve missing credential exit path'i doğrula.

### DÜŞÜK-2 — `SIPTimeoutError.reason="timeout"` reason setinde yok

- Dosya/satır: `services/voice-agent/agent/errors.py:27-38`, `80-85`
- Etki: Kod çalışıyor, ancak dokümante set ile runtime değer uyumsuz.
- Öneri: `SIP_FAILURE_REASONS` içine `timeout` ekle veya ayrı constant yap.

## 25. Staging öncesi zorunlu işlemler

1. Runtime `error` event'ini terminal flow'a bağla ve test et.
2. CompletionGuard retry politikasını permanent/transient hata ayrımıyla düzelt.
3. SIP reason -> backend call status/outcome mapping'i netleştir ve test et.
4. End-call grace yerine mümkünse gerçek speech completion sinyali kullan.
5. Usage delivery failure'ın completion reason'ı bozmasını engelle.
6. Queue drain için explicit graceful shutdown timeout ekle.
7. `~/AI_MEMORY/GLOBAL_STATUS.md` eski Phase 4 bilgisini manuel güncelle.
8. Staging credential/test numarası allowlist hazırlanırken ilk test gerçek müşteri numarasıyla yapılmamalı.

## 26. Sonuç kararı

**ÖNEMLİ DÜZELTMELER GEREKLİ**

Gerekçe:

- Önceki iki kritik bulgu pratikte kapanmış.
- Önceki yüksek bulgulardan completion sessiz yutma, usage wiring ve production adapter test boşluğu kapanmış.
- SIP ayrımı yalnız event payload seviyesinde kaldığı için tam kapanmamış.
- Yeni yüksek riskler var: runtime `error` terminal değil, completion permanent hataları retry ediyor, SIP reason backend sonucuna taşınmıyor.

Bu yüzden `STAGING TESTİNE HAZIR` denemez. Düzeltmeler kapsam olarak sınırlı ama staging kararını etkilediği için "küçük düzeltmeler" değil, önemli düzeltmeler olarak sınıflandırıldı.

## 27. Çalıştırılan komutlar

Git/kapsam:

```text
pwd
git status --short
git diff --stat
git diff --name-only
git log --oneline -5 2>/dev/null || true
```

SDK yüzeyi:

```text
uv run python -c "... AgentSession, CloseReason, RealtimeModel signatures ..."
uv run python -c "... AgentSession usage property ..."
uv run python -c "... LLMModelUsage fields ..."
uv run python -c "... ChatMessage.text_content property ..."
```

Voice-agent:

```text
PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_voice uv run python -m compileall -q agent
RUFF_CACHE_DIR=/tmp/ivac_ruff_voice uv run ruff check agent tests
MYPY_CACHE_DIR=/tmp/ivac_mypy_voice PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_voice uv run mypy agent
PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_voice uv run pytest -q -o cache_dir=/tmp/ivac_pytest_voice
COVERAGE_FILE=/tmp/ivac_voice_coverage PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_voice uv run pytest --cov=agent --cov-report=term-missing -o cache_dir=/tmp/ivac_pytest_voice_cov
PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_voice uv run python -m agent.main --check-config
```

Sonuç:

```text
compileall: geçti
ruff: All checks passed!
mypy: Success: no issues found in 16 source files
pytest: 83 passed in 12.38s
coverage: TOTAL 86%, 83 passed
check-config: dry check valid, runtime credentials missing listesi açıkça yazıldı
```

Backend:

```text
RUFF_CACHE_DIR=/tmp/ivac_ruff_api uv run ruff check app tests
MYPY_CACHE_DIR=/tmp/ivac_mypy_api PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_api uv run mypy app
PYTHONPYCACHEPREFIX=/tmp/ivac_pycache_api uv run pytest -q -o cache_dir=/tmp/ivac_pytest_api
```

Sonuç:

```text
ruff: All checks passed!
mypy: Success: no issues found in 80 source files
pytest: 111 passed, 1 warning in 20.94s
```

Docker:

```text
docker compose -f docker-compose.dev.yml config
docker compose -f docker-compose.dev.yml --profile voice config
```

Sonuç:

```text
normal config: geçti, voice-agent yok
voice profile config: geçti, voice-agent yalnız --check-config komutuyla görünüyor
```

## 28. Değiştirilen dosyalar

```text
CODEX_AUDIT_PHASE_4_FIX.md
```
