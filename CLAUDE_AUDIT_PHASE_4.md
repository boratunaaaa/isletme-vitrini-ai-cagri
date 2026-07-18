# CLAUDE_AUDIT_PHASE_4.md — Bağımsız İkinci Göz Denetimi

Denetleyen: Claude (bağımsız, salt-okunur denetim) · Denetlenen: `services/voice-agent` (LiveKit Agents + OpenAI Realtime + SIP runtime), Phase 4 raporu `CLAUDE_PROGRESS_PHASE_4.md`.

## 1. Yönetici özeti

Voice-agent servisi derleniyor, lint/type/test kapılarından geçiyor (40 test, %78 coverage, Ruff/MyPy temiz) ve düşük seviyeli SDK alan adları (CreateSIPParticipantRequest alanları, RealtimeModel kwargs, RoomOptions/AudioInputOptions) gerçekten kurulu `livekit-agents 1.5.17` / `livekit-api 1.2.0` / `livekit-plugins-openai 1.5.17` / `openai 2.46.0` paketlerine karşı doğrulanmış — bu düzeyde uydurma API yok.

Ancak **çalışma zamanı akışının kalbi kırık**: `VoiceAgentJobHandler.handle()` telefonu arar, açılış cümlesini bir kez söyler ve **hiçbir şeyi beklemeden** anında kullanım verisini "unavailable" işaretleyip görüşmeyi tamamlanmış sayıp `ctx.shutdown()` çağırıyor. Karşı taraf ne derse desin, modelin cevabı dinlenmiyor, hiçbir tool'un çağrılmasına fırsat verilmiyor. Bunu doğrulayan test (`test_job_handler_success_flow`) bu davranışı bizzat "başarı" olarak assert ediyor — yani hata testlerde de yakalanmamış, testin kendisi hatalı davranışı doğru kabul ediyor.

İkinci bağımsız doğrulanmış kritik bulgu: proje genelinde iddia edilen "log redaksiyonu" `logger.exception()` ile atılan traceback'leri korumuyor. Canlı repro ile telefon numarası ve Bearer token'ın log çıktısına düz metin sızdığı gösterildi.

Bu iki bulgu tek başına "Aşama 4 tamamlandı" iddiasını geçersiz kılar: sistem şu anki haliyle gerçek bir telefon görüşmesi YÜRÜTEMEZ (yalnız "merhaba" deyip kapatır) ve loglama güvenlik garantisi kanıtlanabilir şekilde ihlal ediliyor.

## 2. Denetlenen kapsam

- `services/voice-agent/agent/*.py` (15 dosya, 2020 satır) — tamamı satır satır okundu.
- `services/voice-agent/tests/*.py` (6 dosya) — tamamı okundu.
- `services/api/app/api/routes/internal/{common,health,calls,tools}.py`, `services/api/app/schemas/internal/voice_agent.py`, `services/api/app/services/internal_contract.py`, `services/api/app/models/internal.py` (voice-agent'ın konuştuğu backend contract yüzeyi).
- `docs/internal-voice-agent-api.md`, `docs/voice-agent-runtime.md`.
- `docker-compose.dev.yml` (`voice` profili), `infrastructure/docker/voice-agent.Dockerfile`.
- `.env.example`, `services/voice-agent/pyproject.toml`, `uv.lock`.
- `CODEX_AUDIT.md`, `CODEX_PROGRESS_PHASE_{1,2,3}.md`, `CLAUDE_PROGRESS_PHASE_4.md`, `PROJECT_STATUS.md`, `TODO.md`, `CHANGELOG.md`, `~/AI_MEMORY/GLOBAL_STATUS.md` (yalnızca okundu).
- Kurulu `livekit-agents`/`livekit-api`/`livekit-plugins-openai`/`openai` paketlerinin gerçek Python nesneleri `inspect.signature` ile introspect edildi (ağ bağlantısı olmadan, yalnız yerel kurulu paketler üzerinde).
- Statik araçlar: `compileall`, `ruff check`, `mypy`, `pytest` (+coverage), `agent.main --check-config`, `docker compose config` (normal + `voice` profili) — hepsi yerel/offline, harici bağlantı yok.
- Redaksiyon iddiasını doğrulamak için tek bir izole Python repro'su çalıştırıldı (bölüm 14'te detaylı).

Kapsam dışı bırakılan: gerçek LiveKit/OpenAI/Netgsm bağlantısı, gerçek SIP çağrısı, backend regresyon testinin tekrar çalıştırılması (rapor üzerinden değerlendirildi, şüpheli contract uyuşmazlığı bulunmadı).

## 3. Git ve değişiklik durumu

```text
pwd → /Users/kadirugur/Projects/isletme-vitrini-ai-cagri
git status --short → tüm proje dosyaları untracked (?? ile işaretli); repo hâlâ ilk commit öncesi.
git diff --stat / --name-only → boş (izlenen dosya yok, dolayısıyla diff üretilemiyor — beklenen durum).
git log --oneline -5 → boş (hiç commit yok).
```

- Aşama 4 kapsamında oluşturulan asıl dosyalar: `services/voice-agent/**` (agent + tests + pyproject + uv.lock), `infrastructure/docker/voice-agent.Dockerfile`, `docs/voice-agent-runtime.md`, `CLAUDE_PROGRESS_PHASE_4.md`.
- Aşama 4 kapsamında değiştirilen mevcut dosyalar: `docker-compose.dev.yml` (`voice` profili eklendi), `.env.example` (voice-agent runtime değişkenleri eklendi), `PROJECT_STATUS.md`, `TODO.md`, `CHANGELOG.md` (Aşama 4 "tamamlandı" olarak işlendi).
- Proje dışı değişiklik: `~/AI_MEMORY/GLOBAL_STATUS.md` en üste yeni bir "2026-07-18" girişi eklenmiş, "Aşama 4 ... tamamlandı ✅" diyor (bkz. bölüm 17 — bu iddia bu denetimin bulgularıyla çelişiyor).
- Prompt kapsamı dışında değiştirilmiş dosya tespit edilmedi.
- Yanlışlıkla eklenmiş secret/model dosyası/log/transcript taraması: `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage` her iki serviste de mevcut ama hepsi `.gitignore` kapsamında (repo untracked olduğu için zaten git'e giremezler). `.env` dosyası yok, yalnız `.env.example` var ve içi boş placeholder'lardan ibaret — secret sızıntısı yok.

## 4. SDK sürümleri ve gerçek API uyumu

Kurulu sürümler (uv.lock + runtime introspection ile doğrulandı): `livekit==1.1.8`, `livekit-agents==1.5.17`, `livekit-api==1.2.0`, `livekit-plugins-openai==1.5.17`, `livekit-protocol==1.1.19`, `openai==2.46.0`. Rapordaki iddialarla birebir eşleşiyor.

Doğrulanan gerçek API yüzeyleri (uydurma değil):

| Kullanım | Kod konumu | Gerçek imza (introspect) | Sonuç |
|---|---|---|---|
| `AgentServer(ws_url=, api_key=, api_secret=)` | `job_handler.py:247-251` | Var, kwargs eşleşiyor | ✅ |
| `AgentServer.rtc_session(agent_name=...)` | `job_handler.py:253` | `(func=None, *, agent_name='', type=..., on_request=, on_session_end=)` | ✅ |
| `AgentSession(llm=, tools=, max_tool_steps=, allow_interruptions=, min_interruption_duration=, user_away_timeout=)` | `session.py:114-121` | Tüm alanlar gerçek `AgentSession.__init__` imzasında mevcut | ✅ |
| `AgentSession.start(room=, agent=, room_options=)` | `session.py:136-146` | `start(self, agent, *, capture_run=False, room=, room_options=, ...)` — `agent` keyword geçilebilir (pozitif keyword-or-positional), sorun yok | ✅ ama bkz. bulgu KRİTİK-1 (dönüş değeri hiç kullanılmıyor) |
| `openai.realtime.RealtimeModel(model=, voice=, modalities=, api_key=, input_audio_transcription=, turn_detection=, max_session_duration=)` | `session.py:96-112` | Gerçek imzada birebir mevcut | ✅ |
| `room_io.RoomOptions(audio_input=, close_on_disconnect=)`, `room_io.AudioInputOptions(sample_rate=, num_channels=, auto_gain_control=)` | `session.py:139-144` | Gerçek imzalarla eşleşiyor | ✅ |
| `lk_api.CreateSIPParticipantRequest(sip_trunk_id=, sip_call_to=, room_name=, participant_identity=, participant_name=, max_call_duration=, wait_until_answered=, hide_phone_number=)` | `sip.py:57-66` | Gerçek protobuf `DESCRIPTOR.fields` listesinde tüm alanlar mevcut | ✅ |
| `lk_api.SipCallError`, `lk_api.LiveKitAPI`, `client.room.remove_participant`, `client.room.delete_room` | `sip.py` | Mevcut sınıflar | ✅ |
| `function_tool` decorator, `livekit.agents.llm.FunctionTool` | `tools.py` | Mevcut | ✅ |

Sonuç: SDK alan/parametre isimlerinde **uydurma yok**. Sorun API yüzeyinde değil, **akış mantığında** (bkz. bölüm 5).

## 5. LiveKit worker/job runtime

`build_server()` (`job_handler.py:246-269`) her job için yeni bir `InternalAPIClient` açıyor, `VoiceAgentJobHandler.handle(ctx)`'i çağırıp `finally`'de `api.aclose()` yapıyor — kaynak sızıntısı yok, doğru.

`VoiceAgentJobHandler.handle()` (`job_handler.py:124-240`) gerçek akış (satır satır):

1. `_bootstrap(call_id)` → backend'den context alınır.
2. `AGENT_JOB_STARTED` event'i gönderilir.
3. `dial_plan = await api.dial_plan(call_id)`.
4. `await ctx.connect()` — LiveKit odasına bağlanılır.
5. Tool registry + realtime runtime **inşa edilir** (henüz başlatılmaz).
6. `SIP_PARTICIPANT_CREATING`, `DIALING` event'leri gönderilir.
7. `sip_handle = await sip.create_participant(dial_plan)` — bu, `wait_until_answered=True` ile **bloklayan** gerçek SIP çağrısıdır; cevap gelene/reddedilene/timeout'a kadar burada bekler.
8. `RINGING`, (cevaplandıysa) `ANSWERED` event'leri **retroaktif olarak** (çağrı zaten bloklayan `create_participant` içinde sonuçlanmışken) gönderilir.
9. `await realtime.start(runtime, ctx.room)` — `AgentSession.start()` çağrılır (dönen `RunResult`/`None` **hiç okunmuyor/kullanılmıyor**).
10. `AGENT_SESSION_STARTED` event'i gönderilir.
11. `await runtime.opening.play_once_after_answer(runtime.session)` — modele "açılış cümlesini söyle" talimatı verilir (`session.generate_reply(instructions=...)`), dönen `SpeechHandle` **awaitlenmiyor/beklenmiyor** (bu satırın kendisi await'li ama `generate_reply`'nin sesin gerçekten çalınıp bitmesini beklediğine dair hiçbir garanti/kontrol yok — SDK'da bu genelde `SpeechHandle.wait_for_playout()` ile yapılır, burada hiç kullanılmıyor).
12. **HEMEN ARDINDAN**: `usage.report_unavailable(...)` çağrılıp kullanım "final" olarak `unavailable` işaretlenir.
13. `CALL_DISCONNECTED` event'i `{"reason": "agent_completed"}` payload'ıyla gönderilir — **karşı taraf telefonu kapatmadı, agent kendi kendine "bağlantı kesildi" diyor.**
14. `CompletionGuard.complete_once(..., reason=COMPLETED)` çağrılır → backend'e `/complete` gönderilir, çağrı backend'de terminal duruma geçer.
15. `finally`: transcript flush edilir (boş, çünkü hiç konuşma olmadı), `AGENT_SESSION_ENDED` gönderilir, events flush edilir, realtime session kapatılır (`session.aclose()`), SIP participant/room kaldırılır (`hangup`), **`ctx.shutdown("voice-agent-job-finished")` çağrılır.**

Adım 9-15 arasında **karşı tarafın söylediği hiçbir şeyi dinleyen, bekleyen veya bir tool çağrısını/oturum kapanışını bekleyen tek satır kod yok.** Bu, aşağıdaki KRİTİK-1 bulgusudur.

## 6. OpenAI Realtime entegrasyonu

- Model/voice kataloğu backend ile birebir aynı (`gpt-realtime-2.1-mini`, `gpt-realtime-2.1`; 10 voice), hem `agent/config.py` (env validator) hem `agent/models.py` (`ALLOWED_MODELS`/`ALLOWED_VOICES`) hem `session.py`'de (build() içinde) üç kez doğrulanıyor — savunma katmanları doğru.
- `input_audio_transcription=AudioTranscription(model="gpt-realtime-whisper", language="tr")` ve `turn_detection=SemanticVad(type="semantic_vad", create_response=True, eagerness="auto", interrupt_response=True)` gerçek tiplerle kuruluyor (`openai.types.realtime` import edilerek) — doğru pattern, uydurma değil.
- Türkçe instructions `build_runtime_instructions()` ile bootstrap'ten (system_prompt + objective + objection_rules + KB + lead context + kampanya + açılış talimatı) birleştiriliyor; telefon numarası, token, API key eklenmiyor (test `test_prompt_context_excludes_phone_and_secrets` bunu doğruluyor) — doğru.
- **Tool'lar gerçekten modele kayıt ediliyor** (`tools.livekit_tools()` → `AgentSession(tools=livekit_tools)` ve `Agent(tools=livekit_tools)` ikisine de veriliyor) — doğru, ama bkz. bölüm 5: modelin bu tool'ları çağırabileceği bir zaman penceresi pratikte yok.
- **Session shutdown**: `session.aclose()` çağrılıyor — doğru API, ama gerçek bir konuşma hiç başlamadığı için "doğru shutdown" testi anlamsızlaşıyor.
- **Usage callback**: SDK'nın gerçekten usage sağlayıp sağlamadığını kontrol eden `usage_from_sdk_event()` fonksiyonu **var ve izole test edilmiş**, ama **job_handler.py içinde hiçbir yerde çağrılmıyor** (bkz. KRİTİK/YÜKSEK bulgu listesi, madde 4). Gerçek akışta her zaman `report_unavailable()` çağrılıyor — yani gerçek SDK usage event'i gelse bile hiçbir zaman okunmuyor.
- Model tool başarısızlığında: `ToolExecutor.execute()` `TOOL_CALL_FAILED` event'i gönderip `ToolExecutionError` fırlatıyor; `function_tool` sarmalayıcı bunu modele bir hata olarak iletir (LiveKit'in standart tool-error mekanizması) — modelin "cevap uydurması" için özel bir kapı açılmıyor, makul.

## 7. SIP participant akışı

- Telefon yalnız `dial_plan.phone_e164` üzerinden, yalnız `CreateSIPParticipantRequest.sip_call_to` alanına veriliyor; hiçbir yerde loglanmıyor (redaksiyon regex'i `_PHONE_RE` zaten yakalıyor, ayrıca kod telefonu asla `logger`'a geçirmiyor).
- `hide_phone_number=True` gerçek alan, doğru kullanılmış.
- Outbound trunk ID backend'in `dial-plan` response'undan geliyor (`settings.LIVEKIT_SIP_OUTBOUND_TRUNK_ID` — backend env'inden, hard-code yok).
- Room adı/participant identity backend'de deterministik üretiliyor (`f"call-{call.id}"`, `f"phone-{call.id}"`) — job/call başına stabil.
- **Duplicate SIP participant koruması yalnız process-içi bir `set`** (`self._created: set[tuple[uuid, str]]`, `sip.py:44`) — aynı job **instance'ı** ikinci kez `create_participant` çağırırsa (kodda böyle bir çağrı yok, ama savunma amaçlı konmuş) dedupe eder. Ancak bu koruma **yeni bir job/process için sıfırlanır**; gerçek duplicate-dispatch koruması tamamen backend'in `idempotency_key` + aktif-çağrı partial-unique-index'ine dayanıyor (Phase 4 kapsamı dışı ama önemli bir bağımlılık).
- **Timeout var**: `asyncio.wait_for(..., timeout=SIP_PARTICIPANT_TIMEOUT_SECONDS)` — doğru.
- **Dialing/ringing/answered ayrımı SDK event'lerinden DEĞİL, tek bir bloklayan `wait_until_answered=True` çağrısının başında/sonunda sentetik olarak üretiliyor** (bölüm 5, adım 6-8). Gerçek SIP INVITE/180/200 zaman çizelgesi izlenmiyor.
- **Busy/rejected/no-answer/voicemail SDK event'lerinden ayrıştırılamıyor** — `lk_api.SipCallError` yakalanıyor ama `exc.sip_status_code`/`exc.sip_status` **atılıyor**, hepsi tek bir `SIPParticipantError` → `DisconnectReason.SIP_FAILURE`'a indirgeniyor (bkz. YÜKSEK-3).
- Hangup doğru participant/room üzerinde çalışıyor (`remove_participant` varsa identity ile, yoksa `delete_room`), hata yutulup `logger.warning(safe_error_message(exc))` ile güvenli loglanıyor — bu satır doğru yapılmış (bkz. bölüm 10'daki karşılaştırma).
- Netgsm'e özel uydurma varsayım bulunamadı; Netgsm yalnız backend'in `dial-plan` response'undaki `caller_id`/`sip_transport`/`codec_preferences` alanları üzerinden temsil ediliyor, voice-agent Netgsm'i hiç bilmiyor (mimari olarak doğru — Netgsm bilgisi LiveKit outbound trunk konfigürasyonunda yaşamalı, backend response'unda değil).

## 8. Internal API contract uyumu

`services/voice-agent/agent/models.py` ile `services/api/app/schemas/internal/voice_agent.py` satır satır karşılaştırıldı: `BootstrapResponse`, `DialPlanResponse`, `AgentEventType` (20 değer), `LifecycleEventIn`, `TranscriptTurnIn`, `UsageSourceIn` (3 değer), `UsageUpdateIn`, `CompletionIn`, `ToolResponse` alan adları ve tipleri **birebir eşleşiyor**. Endpoint path'leri (`agent/api_client.py`) `docs/internal-voice-agent-api.md`'deki 18 endpoint ile bire bir aynı. Tek fark yok — contract uyumu bu düzeyde temiz.

`InternalAPIClient._request()` hata sınıflandırması da backend hata kodlarıyla tutarlı: `401/403→InternalAPIAuthenticationError`, `409 DUPLICATE_EVENT_CONFLICT→DuplicateConflictError`, `409/4xx CALL_NOT_DIALABLE→CallNotDialableError`, `5xx→retry`. Bu doğru ve iyi düşünülmüş.

## 9. Tool entegrasyonları

12 tool'un tamamı backend path'leriyle birebir eşleşiyor (`tools.py` `TOOL_DEFINITIONS` ↔ `docs/internal-voice-agent-api.md` endpoint listesi). `ToolExecutor.execute()`:
- Her çağrıya benzersiz `tool_call_id` üretiyor (`next_tool_call_id`, sayaç bazlı + tool adı).
- `TOOL_CALL_STARTED`/`COMPLETED`/`FAILED` event'lerini doğru sırayla gönderiyor.
- Backend zaten idempotent (`internal_invocations` unique constraint) — aynı `tool_call_id` tekrar gönderilirse backend eski sonucu döner; ancak voice-agent tarafında `tool_call_id` sayaç bazlı üretildiği için **aynı tool ikinci kez çağrılırsa farklı bir ID üretilir** (idempotency yalnız gerçek ağ retry'larında işliyor, mantıksal "aynı tool'u iki kez çağırma" senaryosunda değil — bu tasarım gereği, sorun değil, model her tool çağrısını yeni bir işlem olarak görmeli zaten).
- Sonuç modele **her zaman kısa, doğal bir Türkçe özet** olarak dönüyor (`summarize_tool_result`), ham JSON asla dönmüyor — `test_tool_summary_is_not_raw_json` bunu doğruluyor. Doğru.
- `end_call_safely` tool'u backend'de yalnız `{"should_hangup": True, "hangup_performed": False}` döndürüyor — **fiili hangup'ı gerçekleştiren hiçbir kod yok**, ne backend'de ne voice-agent'ta. Modele "kısa bir teşekkürle kapat" deniyor ama gerçek hattı kapatacak bir mekanizma bağlı değil (zaten pratikte önemsiz, çünkü bölüm 5'teki bug nedeniyle görüşme bu noktaya hiç ulaşamıyor).
- `request_human_transfer`: backend `HUMAN_TRANSFER_ENABLED=false` iken doğru şekilde `transfer_available: False` döndürüyor (adapter çağrılmıyor) — ama **voice-agent'ın `SIPParticipantAdapter` protokolünde bir `transfer()` metodu bile yok** (yalnız `create_participant`/`hangup` var), yani `HUMAN_TRANSFER_ENABLED=true` olsa bile gerçek bir SIP transfer'i tetikleyecek kod yok. `CLAUDE_PROGRESS_PHASE_4.md` bölüm 28'deki "Human transfer adapter yapısı hazır" ifadesi bu haliyle **yanıltıcı** — yapı hazır değil, yalnız backend flag'i var.

## 10. Transcript akışı

- `QueuedTranscriptSink.enqueue_turn()`: `is_final=False` olan turn'leri **sessizce atlıyor**, kalıcı endpoint'e göndermiyor (`transcript.py:55-56`) — partial transcript sınırsız birikmiyor, doğru.
- Bounded queue (`asyncio.Queue(maxsize=max_size)`), dolarsa `logger.warning(...)` ile drop ediliyor (kritik olmayan veri kaybı, kabul edilebilir tasarım).
- Redaksiyon: `redact_text()` çağrılıyor (telefon/email/Bearer/OpenAI-key regex'leri) **öncesinde** backend'e gönderiliyor — backend ayrıca kendi `redact_text()`'ini de uyguluyor (`internal_contract.py`), çift katman — iyi.
- **Gerçekte hiç transcript üretilmiyor** çünkü bölüm 5'teki bug nedeniyle konuşma hiç gerçekleşmiyor; bu bileşenin kodu doğru ama pratikte kullanılmıyor.

## 11. Usage ve maliyet akışı

- `usage_from_sdk_event()` doğru yazılmış ve izole test edilmiş (yalnız SDK'da gerçekten var olan alanları okuyor, token sayısı uydurmuyor) — **ama production kod yolunda hiçbir yerden çağrılmıyor** (grep ile doğrulandı, sıfır çağrı noktası).
- Gerçek akışta her zaman `usage.report_unavailable(model=..., is_final=True)` çağrılıyor (`job_handler.py:164-167`) — backend bunu `usage_source=unavailable` olarak kabul ediyor (hata vermiyor, `PRICING_NOT_CONFIGURED` tetiklenmiyor çünkü backend özellikle `usage_source != UNAVAILABLE` durumunda pricing zorunlu kılıyor — `calls.py:396`), ama **maliyet asla hesaplanmıyor**, panelde her görüşme için maliyet hep boş/0 kalacak. Bu, orijinal spesifikasyonun 28. bölümündeki "her görüşmenin tahmini maliyetini gösterecek" zorunluluğunu fiilen karşılamıyor.
- Sonuç: maliyet/kullanım altyapısı (backend tarafı doğru kurulmuş) voice-agent tarafında **hiç beslenmiyor**.

## 12. Completion ve shutdown

- `CompletionGuard.complete_once()` aynı job içinde tek seferlik completion garantisi **veriyor gibi görünüyor** ama gerçekte bir güvenlik açığı içeriyor: `self._completed = True` bayrağı, backend'e giden `await api.complete(...)` çağrısından **ÖNCE** set ediliyor (`job_handler.py:90-92`). Eğer bu API çağrısı başarısız olursa (`CompletionError` fırlatılır), bu istisna hiçbir spesifik `except` bloğuna girmez (`CallNotDialableError`/`SIPParticipantError`/`RealtimeSessionError` değildir), genel `except Exception:` bloğuna düşer — o blok da `complete_once(...)`'u **tekrar çağırır**, ama guard zaten `_completed=True` olduğu için bu ikinci çağrı **sessizce hiçbir şey yapmadan döner**. Sonuç: `/complete` teslimatı başarısız olan bir görüşme, backend tarafında **sonsuza kadar terminal olmayan bir durumda** kalır (örn. `agent_active`), voice-agent hiçbir zaman tekrar denemez ve bu durumu ayrı bir alarmla işaretlemez (yalnız `logger.exception` ile loglar — ki o da bölüm 14'teki redaksiyon açığına tabi). Bu senaryoyu test eden hiçbir test yok.
- Remote hangup / agent hangup arasında bir "race" **oluşamıyor çünkü remote hangup'ı dinleyen hiçbir kod yok** — bu aslında bölüm 5'teki ana bug'ın bir başka yansıması: sistem gerçek bir "remote hangup" event'ini hiç işlemiyor, yalnız kendi ürettiği sentetik "agent_completed" nedenini kullanıyor.
- Shutdown sırasında transcript/usage kaybı: `finally` bloğu `transcript.flush()` ve `events.flush()` çağırıyor (kuyruktaki mevcut öğelerin teslim edilmesini bekliyor) ama **arka plan tüketici task'larını (`_task`) hiç durdurmuyor/iptal etmiyor** — `stop()` metodu var ama çağrılmıyor, yalnız `flush()` çağrılıyor (bkz. bölüm 13, ORTA bulgu).
- Maksimum çağrı süresi: `max_session_duration` RealtimeModel'e geçiliyor (SDK seviyesinde bir üst sınır) ve `SIP_PARTICIPANT_TIMEOUT_SECONDS`/`REALTIME_STARTUP_TIMEOUT_SECONDS` ayrı ayrı uygulanıyor — bunlar doğru, ama pratikte hiç işlemiyor çünkü görüşme zaten saniyeler içinde (açılış cümlesi kadar) kendi kendine bitiyor.

## 13. Async/concurrency bulguları

- **Arka plan tüketici task'ları asla iptal edilmiyor** (`LifecycleEventDispatcher._run()`, `QueuedTranscriptSink._run()`): her ikisinin de `stop()` metodu (task cancel + `CancelledError` yutma) tanımlı ama `job_handler.py` yalnız `flush()` çağırıyor. `job_executor_type=PROCESS` varsayılanında process job sonunda öldüğü için pratik etkisi sınırlı, ama bu, sınıfın kendi API sözleşmesiyle çelişen bir kullanım hatası ve `job_executor_type` ileride `thread`/`inline` gibi paylaşımlı bir moda geçerse gerçek bir task/kaynak sızıntısına dönüşür. **ORTA**.
- **`idempotent()` (backend, `internal_contract.py:75-110`) SELECT-then-INSERT deseni kullanıyor, transaction seviyesinde kilit yok.** DB'de `UniqueConstraint(call_id, external_id)` var (`models/internal.py:16`) ama `idempotent()`'in hiçbir yerinde bu constraint ihlalinin (`IntegrityError`) yakalandığı bir `except` yok — iki eşzamanlı istek (örn. voice-agent'ın HTTP retry'ı ile orijinal istek yarışırsa) aynı `external_id` ile ikisi de "existing yok" görüp ikisi de `handler()`'ı çalıştırabilir; ikincisi `db.flush()`'ta `IntegrityError` ile patlar ve bu, route'larda yakalanmadığı için **500** olarak voice-agent'a döner (temiz `409 DUPLICATE_EVENT_CONFLICT` yerine). Voice-agent tarafında bu, `InternalAPIContractError` olarak sınıflandırılır (retry edilmez) — akış kırılmaz ama hata sınıflandırması yanlış ve gürültülü olur. **ORTA**.
- Unawaited coroutine / fire-and-forget task kaybı: bulunamadı — tüm `asyncio.create_task` çağrıları (`events.py:45`, `transcript.py:42`) referansları saklıyor.
- `LiveKitAPI`/`httpx.AsyncClient` kapatma: `sip.py`'de her `create_participant`/`hangup` çağrısı kendi `LiveKitAPI` client'ını açıp `finally`'de `aclose()` ediyor — doğru ama her çağrıda yeni TCP/gRPC bağlantısı açılıp kapatılıyor (performans notu, güvenlik sorunu değil, **DÜŞÜK**).
- Blocking I/O event loop içinde: bulunamadı; tüm ağ çağrıları `httpx.AsyncClient`/`LiveKitAPI` async metodları üzerinden.
- Deadlock/sonsuz bekleme: bulunamadı; tüm `wait_for`'lar timeout'lu.

## 14. PII ve secret güvenliği

**KRİTİK — canlı repro ile doğrulandı.** `agent/logging.py`'deki `RedactionFilter.filter()` yalnız `record.msg` (str) ve `record.args` (dict/tuple) üzerinde `safe_value()`/`redact_text()` çalıştırıyor. `record.exc_info` (traceback) **hiç dokunulmuyor**. `job_handler.py:217`'deki genel hata yakalama bloğu `logger.exception("Voice-agent job failed")` çağırıyor — bu, Python logging'in `exc_info=True` davranışıyla **tam traceback'i redaksiyonsuz** basar.

Repro (bu ortamda, harici bağlantı olmadan çalıştırıldı):

```python
from agent.logging import configure_logging
configure_logging('INFO')
try:
    raise RuntimeError('internal api call failed for +905551112233 with token Bearer sk-ABCDEFGHIJKLMNOPQRSTUVWX')
except RuntimeError:
    logging.getLogger('agent.reproduce').exception('Voice-agent job failed')
```

Çıktı (özet):
```
RuntimeError: internal api call failed for +905551112233 with token Bearer sk-ABCDEFGHIJKLMNOPQRSTUVWX
=== CONTAINS PHONE === True
=== CONTAINS TOKEN === True
```

Telefon numarası VE Bearer token, redaksiyon aktifken loglara düz metin olarak sızdı. Bu, `docs/voice-agent-runtime.md`'nin açıkça verdiği garantiyle ("Log filter token, API key, telefon ve email benzeri hassas değerleri redakte eder") doğrudan çelişiyor.

Ayrıca iki log call-site ham exception'ı `safe_error_message()`'dan geçirmeden `%s` argümanı olarak veriyor (`events.py:86`, `transcript.py:88`) — `RedactionFilter.safe_value()` `str`/`Mapping`/`Sequence` dışındaki tipleri (ör. `Exception` nesnesi) **olduğu gibi bırakıyor** (`redaction.py:34-48`), bu da aynı sınıf açığın ikinci somut örneği.

Backend tarafı karşılaştırma: `services/api/app/core/logging.py`'deki `JsonFormatter.format()` **özellikle** `record.exc_info` içeriğini `redact(self.formatException(record.exc_info))` ile temizliyor — yani bu proje için doğru desen zaten backend'de var, voice-agent'ın kendi (ayrı yazılmış) logging modülü bu deseni **tekrar etmemiş**.

Diğer PII/secret kontrolleri:
- `OPENAI_API_KEY`, `INTERNAL_SERVICE_TOKEN`, `LIVEKIT_API_SECRET`: hepsi `SecretStr` olarak tutuluyor (`config.py`), yalnız `.get_secret_value()` ile gerçek kullanım anında okunuyor, `print`/`logger`'a asla geçmiyor (kontrol edildi, ihlal yok bu üç değişken için spesifik olarak — bulunan sızıntı yolu yalnız serbest metin exception mesajları üzerinden).
- Netgsm/SIP password: voice-agent'a hiç ulaşmıyor (backend `dial-plan` response'unda yok, doğrulandı — `TelephonyContext` şemasında `sip_transport`/`codec_preferences`/`caller_id` var, credential yok).
- Tam telefon numarası: yalnız `dial_plan.phone_e164` alanında bellekte taşınıyor, `CreateSIPParticipantRequest`'e veriliyor, hiçbir log/event/transcript'e yazılmıyor **redaksiyon bug'ı hariç**.
- System prompt: loglanmıyor.
- Callback zamanı / işletme bilgileri: yalnız backend'e giden request body'lerinde (`model_dump(mode="json")`), loglara değil.

## 15. Docker yapılandırması

- `docker compose -f docker-compose.dev.yml config` → yalnız `postgres`+`redis` (voice profili varsayılanda YOK) — doğru, dev ortamında yanlışlıkla gerçek aramayı tetiklemiyor.
- `docker compose -f docker-compose.dev.yml --profile voice config` → `voice-agent` eklenir, `command: ["python", "-m", "agent.main", "--check-config"]` — yani `voice` profili bile açılsa, **gerçek worker'ı değil yalnız config doğrulamasını başlatıyor** (`restart: "no"`). Bu, "development profile gerçek aramayı yanlışlıkla başlatabilir mi?" sorusuna açıkça **HAYIR** cevabını veriyor — iyi tasarlanmış bir güvenlik varsayılanı.
- Dockerfile: multi-stage (`builder`→`runtime`), `uv sync --frozen` kullanılıyor (lock dosyasına sadık, sürüm kayması yok), runtime imajına derleme araçları taşınmıyor (apt paketi kurulmuyor, `uv` yalnız builder'da).
- **Non-root**: `addgroup voiceagent && adduser --system --ingroup voiceagent voiceagent`, `USER voiceagent` — doğru.
- Secret image'a bake edilmiyor — `ENV` bloğunda yalnız `VOICE_AGENT_ENV=production` gibi secret olmayan değerler var; gerçek secret'lar compose'da `${VAR:-}` ile runtime'da enjekte ediliyor.
- **Healthcheck yanlış/eksik anlamlı**: `HEALTHCHECK ... CMD python -m agent.main --check-config || exit 1` — bu yalnız **environment değişkenlerinin dolu olup olmadığını** kontrol ediyor (`_check_config()`, `agent/main.py:11-24`), LiveKit'e gerçekten bağlanabildiğini, worker'ın job alabildiğini veya OpenAI'a erişebildiğini DOĞRULAMIYOR. Prod'da container "healthy" görünürken worker LiveKit'e hiç bağlanamıyor olabilir (yanlış pozitif sağlık sinyali). **ORTA bulgu** — brief'in "`--check-config` healthcheck olarak yanlış kullanılmıyor" sorusuna cevap: **kısmen yanlış kullanılıyor**, yalnızca config-tamlığını ölçüyor, runtime sağlığını değil.
- API/LiveKit hostname'leri: `INTERNAL_API_BASE_URL: http://api:8000` — compose network'te `api` servisi şu an tanımlı değil (yalnız `postgres`/`redis`/`livekit`/`livekit-sip`/`voice-agent` var); bu referans ileride API servisi compose'a eklendiğinde çalışacak, şu an yalnız `--check-config` komutu ağ bağlantısı denemediği için sorun çıkarmıyor. **DÜŞÜK/bilgi notu**, gerçek `voice-agent` worker komutuyla (`python -m agent.main`, argümansız) çalıştırılırsa `api` servisi yoksa bağlantı hatası verir — bu beklenen ve mevcut geliştirme aşamasında zaten kapsam dışı.
- Restart policy: `unless-stopped` (postgres/redis/livekit/livekit-sip), `"no"` (voice-agent, tek seferlik check komutu için doğru).

## 16. Test kalitesi

40 test gerçekten geçiyor (doğrulandı: `pytest -q` → `40 passed in 2.98s`, coverage `%78` — rapordaki rakamlarla birebir aynı).

Ancak testlerin neyi **doğrulamadığı**, neyi doğruladığından daha önemli:

- **`test_job_handler_success_flow` (`tests/test_job_handler.py:83-102`) bölüm 5'teki kritik hatalı davranışı "başarı" olarak assert ediyor**: `assert len(realtime.runtime.session.replies) == 1` ve `assert len(api.completions) == 1` — yani test, "agent bir kere konuşup hemen kapatır" davranışını doğru kabul ediyor. Çok turlu bir konuşma, kullanıcı girdisi, tool çağrısı sonrası devam eden bir senaryo **hiç yok**. Bu yüzden testler geçse de gerçek davranışı ölçmüyorlar — testler kodun **niyetini değil mevcut (kırık) halini** doğruluyor.
- **`LiveKitRealtimeSessionAdapter` ve `LiveKitSIPParticipantAdapter` (gerçek prod adapter sınıfları) hiçbir testte instantiate edilmiyor** (grep ile doğrulandı: `tests/` içinde sıfır referans). Coverage raporu bunu teyit ediyor: `session.py` satır 90-127 (gerçek `RealtimeModel` inşası) ve `sip.py` satır 43-97 (gerçek `CreateSIPParticipantRequest`/`LiveKitAPI` çağrısı) **MISS** olarak işaretli. Yalnız `Fake*` sürümleri test ediliyor. SDK yükseltmesi veya kwarg hatası bu iki dosyada olursa hiçbir test kırılmaz.
- `usage_from_sdk_event()` izole test edilmiş ve doğru çalıştığı kanıtlanmış — ama onu **çağıran** kodun var olmadığını yakalayacak bir entegrasyon/"wiring" testi yok (bkz. bölüm 11).
- Tool testleri (`test_tools.py`) `ToolExecutor.execute()`'u iyi kapsıyor (12 tool'un hepsi parametrize test ediliyor) ama `tools.py:220-304` (`@function_tool` dekoratörlü gerçek closure'lar, yani modele KAYIT EDİLEN fonksiyonların gerçek imzaları) coverage'da **MISS** — modelin çağıracağı gerçek fonksiyon imzalarının (`schedule_callback(callback_at: str, notes: str | None = None)` gibi) doğru olduğunu doğrulayan bir test yok.
- Secret/telefon log capture testi **var ama eksik**: `test_phone_response_not_in_logger_message` yalnız `logger.warning(msg, {dict})` senaryosunu test ediyor; `logger.exception(...)` + traceback senaryosunu test etmiyor — tam da bölüm 14'teki KRİTİK açığın kaçırıldığı nokta.
- Duplicate completion race testi yok, remote/agent hangup yarışı testi yok (böyle bir mekanizma zaten kodda olmadığı için test de yok — tutarlı ama eksik).
- SIP request'in gerçek protobuf tipine dönüştüğü doğrulanmıyor testte (yalnız introspection ile bu denetimde doğrulandı, CI'da otomatik değil).

**Sonuç**: %78 coverage rakamı yanıltıcı bir güven verebilir — kapsanmayan %22, projenin en riskli, en "gerçek" kısımlarını (gerçek SDK adapter inşası, gerçek SIP isteği, generic exception handling, main.py/build_server) içeriyor.

## 17. Kapsam dışı dosya değişiklikleri

- `PROJECT_STATUS.md`, `TODO.md`, `CHANGELOG.md`: hepsi "Aşama 4 tamamlandı ✅" diyor, hiçbiri konuşma döngüsünün eksik olduğuna dair bir uyarı/bilinen-sorun notu içermiyor. `PROJECT_STATUS.md`'nin "Riskler" bölümü yalnız "gerçek SIP/OpenAI/LiveKit runtime davranışı credential olmadan doğrulanmadı" diyor — ama bu denetim, credential OLMADAN BİLE, mevcut kodun **credential varsa bile** konuşamayacağını (bölüm 5) statik olarak kanıtladı. Bu, "tamamlandı" iddiasının **aşırı iddialı/overclaiming** olduğu anlamına geliyor.
- `~/AI_MEMORY/GLOBAL_STATUS.md` (proje dışı, kalıcı hafıza dosyası) da aynı "tamamlandı ✅" ifadesiyle güncellenmiş. Bu dosyanın proje dışı olması ve gelecekteki oturumların (Claude/Codex/ChatGPT) bu özet üzerinden "Aşama 4 bitti, Aşama 5'e geç" kararı alabilecek olması riskli: **yanlış/eksik durum bilgisiyle sonraki ajanları yanıltabilir.** Proje-dışı kalıcı hafızayı güncellemek prensipte uygundu (proje kuralları bunu istiyor) ama içeriğin doğruluğu bu denetimin bulgularıyla çelişiyor; güncellemenin *kendisi* değil, **içeriğinin iyimserliği** sorunlu.
- Tamamlanmamış entegrasyonu tamamlanmış gösteren en somut ifade: `CHANGELOG.md` → "LiveKit Agents worker/job runtime, OpenAI Realtime adapter ve LiveKit SIP participant adapter eklendi" — teknik olarak doğru (kod var) ama bu adapter'ların **birlikte çalışarak gerçek bir görüşme yürütemediği** belirtilmiyor.

## 18. Kritik bulgular

### KRİTİK-1 — Agent hiçbir gerçek konuşma yürütmüyor; açılış cümlesinden hemen sonra görüşmeyi kendi kendine sonlandırıyor

- **Dosya/satır**: `services/voice-agent/agent/job_handler.py:161-179` (ana akış), `:229-240` (finally/shutdown), destekleyici: `agent/session.py:62-67` (`OpeningGate.play_once_after_answer`, dönüş değeri/`SpeechHandle` beklenmiyor).
- **Sorun**: `realtime.start()` → tek bir `generate_reply()` (açılış) → hemen `usage.report_unavailable(is_final=True)` → `CALL_DISCONNECTED` → `complete_once(reason=COMPLETED)` → `finally`'de `session.aclose()` + SIP hangup + `ctx.shutdown()`. Karşı tarafın konuşmasını dinleyen, bir tool çağrısını bekleyen, oda/oturum kapanış event'ini dinleyen **hiçbir kod yok** (grep ile doğrulandı: `session.on(`/`room.on(`/`asyncio.Event` hiç yok).
- **Gerçek etkisi**: Her gerçek arama, karşı taraf cevap verse bile, agent'ın açılış cümlesini söylemesinin hemen ardından kapanır. Görüşme hiçbir zaman gerçekleşmez. Backend tarafında (`services/api/app/api/routes/internal/calls.py:490-491` + `derive_fallback_outcome`) bunun sonucu: `call.outcome` hiç set edilmediği (hiçbir tool çağrılmadığı) için her cevaplanan arama otomatik olarak `follow_up_required` outcome'una düşer — sistemin asıl amacı olan lead sınıflandırması (ilgili/ilgisiz/demo istedi/aramayın vb.) fiilen çalışmaz.
- **Kanıt**: Kod okuması + gerçek SDK introspection'ı (`AgentSession.start()`/`generate_reply()` dönüş değerlerinin kullanılmadığı doğrulandı) + `tests/test_job_handler.py:83-102`'nin bu davranışı `assert len(replies)==1` ile "başarı" olarak doğrulaması (yani test bug'ı örtbas ediyor, yakalamıyor).
- **Önerilen çözüm**: `handle()`'a, açılıştan sonra gerçek görüşme süresince bekleyen bir mekanizma eklenmeli — örn. `AgentSession.start(capture_run=True)` ile dönen `RunResult`'ı awaitlemek, veya `finalize_call_outcome`/`end_call_safely` tool çağrısını ya da oda/participant `disconnected` event'ini sinyalleyen bir `asyncio.Event` + üst sınır olarak `max_call_duration_seconds` timeout'u ile `asyncio.wait_for` kombinasyonu. `CALL_DISCONNECTED`/`complete_once` çağrısı yalnız bu bekleme bittiğinde (gerçek hangup, gerçek `finalize_call_outcome`/`end_call_safely`, veya timeout) tetiklenmeli.
- **Kim düzeltmeli**: Claude (voice-agent runtime'ın asıl yazarı) — bu, SDK'nın `AgentSession`/job lifecycle modelinin doğru anlaşılmasını gerektiren mimari bir düzeltme.

### KRİTİK-2 — `logger.exception()` traceback'i redaksiyondan geçmiyor; telefon numarası ve Bearer token loglara düz metin sızabiliyor

- **Dosya/satır**: `services/voice-agent/agent/logging.py:9-18` (`RedactionFilter.filter()` yalnız `record.msg`/`record.args`'a dokunuyor, `record.exc_info`'ya dokunmuyor), tetikleyici çağrı: `agent/job_handler.py:217` (`logger.exception("Voice-agent job failed")`); ikincil örnekler: `agent/events.py:86`, `agent/transcript.py:88` (ham `exc` nesnesi `safe_error_message()`'dan geçirilmeden `%s` argümanı olarak loglanıyor; `redaction.py:34-48`'deki `safe_value()` `Exception` gibi str/Mapping/Sequence-dışı tipleri redakte etmeden aynen döndürüyor).
- **Gerçek etkisi**: Beklenmeyen herhangi bir hata (ki KRİTİK-1'in kırdığı akış göz önüne alındığında bu genel `except Exception` bloğunun tetiklenme ihtimali düşük değil) tam traceback'i, içinde telefon numarası veya token geçen bir exception mesajıyla birlikte, **redaksiyon aktifken bile** düz metin olarak stdout/log altyapısına yazabilir.
- **Kanıt**: Bu ortamda gerçek `configure_logging()` + `logger.exception()` ile canlı repro yapıldı (bölüm 14) — hem `+905551112233` hem `Bearer sk-ABCDEFGHIJKLMNOPQRSTUVWX` çıktıda **aynen** bulundu.
- **Önerilen çözüm**: `RedactionFilter.filter()` içine `record.exc_info` işleme eklenmeli (backend'in kendi `app/core/logging.py`'deki `JsonFormatter.format()`'ının yaptığı gibi: `formatException(record.exc_info)` çıktısını `redact_text()`'ten geçirip ya `record.exc_info = None` yapıp redakte edilmiş metni `record.msg`'e eklemek ya da özel bir `Formatter` kullanmak). Ayrıca `events.py`/`transcript.py`'deki ham `exc` loglamaları `safe_error_message(exc)`'e çevrilmeli; `safe_value()` bilinmeyen tipler için `str(value)`'yu redakte edip döndürecek şekilde genişletilmeli (fail-safe varsayılan).
- **Kim düzeltmeli**: Claude (voice-agent logging modülünün yazarı).

## 19. Yüksek bulgular

### YÜKSEK-1 — `/complete` API çağrısı başarısız olursa CompletionGuard bunu sessizce yutuyor, çağrı backend'de sonsuza kadar terminal olmayan durumda kalabiliyor

- **Dosya/satır**: `agent/job_handler.py:81-107` (`CompletionGuard.complete_once` — `self._completed=True` satır 92, `await api.complete(...)` satır 96, ikisi arasında hata payı yok) + `:216-228` (genel `except Exception` bloğu, `complete_once`'u ikinci kez çağırıyor ama guard zaten kilitli).
- **Gerçek etkisi**: `/complete` teslimatı ağ hatası/backend 5xx/timeout nedeniyle başarısız olursa, voice-agent bunu bir kez loglar (KRİTİK-2'nin redaksiyon açığına da tabi) ve sessizce pes eder; backend'deki `Call` satırı `agent_active` gibi aktif bir durumda asılı kalır. Yalnız backend'in ayrı bir watchdog/sweep mekanizması varsa (bu denetim kapsamında doğrulanmadı) zamanla temizlenir.
- **Kanıt**: Kontrol akışı satır satır izlendi (bölüm 12); bu senaryoyu test eden hiçbir test yok.
- **Önerilen çözüm**: `_completed` bayrağı yalnız `api.complete()` **başarılı** olduktan sonra `True` yapılmalı; başarısızlıkta retry (sınırlı sayıda, backoff'lu) denenmeli veya en azından ayrı, yüksek öncelikli bir alarm event'i üretilmeli.
- **Kim düzeltmeli**: Claude.

### YÜKSEK-2 — `usage_from_sdk_event()` gerçek akışta hiç çağrılmıyor; maliyet takibi fiilen devre dışı

- **Dosya/satır**: `agent/usage.py:47-74` (fonksiyon tanımlı, test edilmiş) — `agent/job_handler.py` içinde sıfır çağrı (grep ile doğrulandı).
- **Gerçek etkisi**: Gerçek OpenAI Realtime kullanım verisi asla backend'e taşınmıyor; her görüşme `usage_source=unavailable` olarak işaretleniyor, maliyet her zaman hesaplanamıyor. Spesifikasyonun "her görüşmenin tahmini maliyetini gösterme" zorunluluğu (bölüm 28) fiilen karşılanmıyor.
- **Kanıt**: Statik grep + `CLAUDE_PROGRESS_PHASE_4.md` bölüm 13'ün ("SDK usage varsa gerçek alanlar çıkarılıyor") iddiasıyla doğrudan çelişen kod okuması.
- **Önerilen çözüm**: Gerçek konuşma döngüsü eklendiğinde (KRİTİK-1 çözümüyle birlikte), `AgentSession`'ın usage/metrics event'lerine (`SessionUsageUpdatedEvent` — gerçek SDK'da mevcut, `dir(agents)` çıktısında görüldü) abone olup `usage_from_sdk_event()`'i gerçekten çağıran bir dinleyici eklenmeli.
- **Kim düzeltmeli**: Claude.

### YÜKSEK-3 — SIP başarısızlık nedenleri (busy/no-answer/voicemail/rejected) ayrıştırılmıyor, hepsi "sip_failure"a indirgeniyor

- **Dosya/satır**: `agent/sip.py:74-77` (`except lk_api.SipCallError as exc: raise SIPParticipantError(...)` — `exc.sip_status_code`/`exc.sip_status` okunmuyor/iletilmiyor).
- **Gerçek etkisi**: Backend'in retry motoru (`services/api/app/services/call_policy.py::compute_next_retry`, Phase 1-2'de doğrulanmış) busy/no_answer/voicemail için farklı bekleme çarpanları uyguluyor — ama voice-agent bu ayrımı hiç sağlamadığı için gerçek aramalarda bu farklılaştırma **hiç işlemeyecek**, her başarısız arama aynı jenerik "sip_failure" yoluna düşecek.
- **Kanıt**: `docs/sip` araştırmasında (bu oturumun erken aşamasında doğrulanan resmi LiveKit örneği) `SipCallError`'ın `sip_status_code`/`sip_status` taşıdığı zaten teyitliydi; kod bunu bilerek/bilmeyerek atıyor.
- **Önerilen çözüm**: `SIPParticipantError`'a `sip_status_code` alanı eklenip `job_handler.py`'de bu koda göre `DisconnectReason`/event payload'ı zenginleştirilmeli; backend event ingestion'ı bu ayrımı `CallOutcome`'a (busy/no_answer/voicemail) yansıtacak şekilde genişletilmeli (bu, Phase 3 backend contract'ında henüz yok — yeni alan gerektirir).
- **Kim düzeltmeli**: Claude (voice-agent) + Codex (backend contract genişletmesi gerekirse).

### YÜKSEK-4 — Prod adapter sınıfları (`LiveKitRealtimeSessionAdapter`, `LiveKitSIPParticipantAdapter`) hiçbir testte kullanılmıyor

- **Dosya/satır**: `agent/session.py:85-156`, `agent/sip.py:41-118` — coverage raporunda bu aralıklar MISS.
- **Gerçek etkisi**: SDK yükseltmesi, kwarg değişikliği veya bir yeniden düzenleme bu iki dosyadaki gerçek üretim kodunu kırabilir ve CI bunu **yakalamaz** (yalnız Fake* sürümleri test ediliyor).
- **Kanıt**: `grep -rn "LiveKitRealtimeSessionAdapter\|LiveKitSIPParticipantAdapter" tests/` → sıfır sonuç; coverage raporu (bölüm 16).
- **Önerilen çözüm**: En azından `LiveKitRealtimeSessionAdapter.build()`'ı gerçek `openai.realtime.RealtimeModel`/`AgentSession` nesneleriyle (ağ çağrısı yapmadan, yalnız construct ederek) çağıran bir test eklenmeli; `LiveKitSIPParticipantAdapter._create_with_client`'ın ürettiği `CreateSIPParticipantRequest`'in beklenen alanlara sahip olduğunu doğrulayan bir test (gerçek `lk_api.LiveKitAPI` client'ı mock'lanarak) eklenmeli.
- **Kim düzeltmeli**: Claude.

## 20. Orta ve düşük bulgular

**ORTA**

- Arka plan tüketici task'ları (`LifecycleEventDispatcher`/`QueuedTranscriptSink`) `stop()` yerine yalnız `flush()` ile kapatılıyor; task'lar iptal edilmiyor (`job_handler.py:230-232`). *(bölüm 13)*
- Backend `idempotent()` fonksiyonu SELECT-then-INSERT yarışında oluşabilecek `IntegrityError`'ı yakalamıyor; nadir eşzamanlı retry senaryosunda temiz `409` yerine `500` dönebilir. *(bölüm 13, `services/api/app/services/internal_contract.py:75-110`)*
- Docker healthcheck (`--check-config`) yalnız env doğruluyor, gerçek LiveKit/OpenAI erişilebilirliğini doğrulamıyor — "healthy" yanlış pozitif riski. *(bölüm 15)*
- `end_call_safely`/`request_human_transfer` tool'larının **gerçek** bir hattı kapatma/aktarma eylemi tetikleyen kod karşılığı yok (yalnız niyet/flag döndürüyorlar); `SIPParticipantAdapter` protokolünde `transfer()` metodu hiç tanımlı değil. *(bölüm 9)*

**DÜŞÜK**

- `sip.py`'deki her `create_participant`/`hangup` çağrısı ayrı bir `LiveKitAPI` client'ı açıp kapatıyor (bağlantı yeniden kullanımı yok) — performans notu.
- DIALING/RINGING/ANSWERED event'leri gerçek SIP zaman çizelgesini değil, tek bir bloklayan çağrının öncesini/sonrasını yansıtıyor — bilgi amaçlı event'ler için kabul edilebilir ama "gerçek zamanlı" izlenim yanıltıcı olabilir.
- `docs/internal-voice-agent-api.md`'deki "Örnek Agent Lifecycle" (8 adım, tool çağrısı dahil) mevcut kodla asla gerçekleşemiyor (KRİTİK-1 nedeniyle) — dokümantasyon güncel koddan daha iyimser bir senaryo anlatıyor.
- `docker-compose.dev.yml`'deki `voice-agent` servisi `INTERNAL_API_BASE_URL: http://api:8000` referans veriyor ama compose'da henüz bir `api` servisi tanımlı değil — yalnız `--check-config` komutuyla zararsız, gelecekte gerçek worker komutuyla çalıştırıldığında hatırlatılması gereken bir bağımlılık.

## 21. Eksik testler

- Çok turlu bir konuşma senaryosu (kullanıcı konuşur → model yanıtlar → tool çağrılır → görüşme doğal olarak biter) simüle eden entegrasyon testi — **bu, KRİTİK-1'in neden yakalanmadığını açıklayan en önemli eksik.**
- `LiveKitRealtimeSessionAdapter.build()`/`start()` ve `LiveKitSIPParticipantAdapter.create_participant()`'ı gerçek (ama mock'lu network'lü) sınıflarla çağıran testler.
- `/complete` API çağrısının bizzat başarısız olduğu senaryo (CompletionGuard'ın sessiz yutma davranışını doğrulayacak/kıracak test).
- `logger.exception()` + traceback'in redaksiyondan geçtiğini doğrulayan test (mevcut tek test yalnız `logger.warning` + dict argümanını kapsıyor).
- `SipCallError.sip_status_code`'ın okunup okunmadığını/okunmasının gerektiğini doğrulayan test.
- Event/transcript kuyruğu sürekli teslimat hatası verirse (`_run()` loop'unun sonsuz retry/log döngüsüne girip girmediği) davranışını doğrulayan test.
- `usage_from_sdk_event()`'in gerçek akışa bağlı olduğunu doğrulayan (şu an bağlı olmadığını yakalayacak) bir "wiring" testi.
- Backend `idempotent()`'in eşzamanlı çağrı yarışını (iki thread/task aynı external_id ile) doğrulayan test.

## 22. Staging öncesi zorunlu düzeltmeler

1. **KRİTİK-1** çözülmeden (gerçek konuşma döngüsü/bekleme mekanizması eklenmeden) **staging'de tek bir test araması bile anlamlı değildir** — her arama aynı şekilde "merhaba" deyip kapanacaktır.
2. **KRİTİK-2** çözülmeden staging/prod loglarına gerçek test numaraları ve/veya token'lar düz metin yazılabilir — güvenlik/gizlilik riski, canlı teste geçmeden düzeltilmeli.
3. **YÜKSEK-1** (completion guard) en azından bir log/alarm ile görünür kılınmalı; sessiz yutma staging'de "neden bazı çağrılar hiç tamamlanmıyor" sorusunu teşhis edilemez hale getirir.
4. **YÜKSEK-2** (usage wiring) staging'de gerçek maliyetlerin görülebilmesi için gerekli; aksi halde "her arama 0$ maliyetli" gibi yanıltıcı bir izlenim oluşur.

## 23. Önerilen düzeltme sırası

1. KRİTİK-1 (konuşma döngüsü) — bu, sistemin var olma amacı; diğer her şey bunun üzerine inşa edilir.
2. KRİTİK-2 (log redaksiyonu) — güvenlik, bağımsız ve hızlı düzeltilebilir (izole, küçük değişiklik).
3. YÜKSEK-1 (completion guard) — KRİTİK-1 ile aynı dosyada, birlikte ele alınabilir.
4. YÜKSEK-2 (usage wiring) — KRİTİK-1 çözümüyle doğal olarak birlikte gelir (gerçek session event dinleyicisi eklenince usage event'leri de aynı yerden akar).
5. YÜKSEK-3 (SIP hata ayrımı) — KRİTİK-1'den bağımsız, orta vadede.
6. YÜKSEK-4 + ORTA bulgular (test kapsamı, task cleanup, healthcheck, idempotency race) — düzeltmeler tamamlandıktan sonra sertleştirme turu olarak.

## 24. Sonuç kararı

**VOICE RUNTIME YENİDEN ELE ALINMALI**

Gerekçe: "Aşama 4"ün amacı, gerçek bir sesli görüşme yürütebilen bir voice-agent kurmaktı. Kod, LiveKit/OpenAI SDK'sının doğru fonksiyon/parametre isimlerini kullanıyor (uydurma API yok) ve etrafındaki altyapı (typed client, redaksiyon niyeti, tool sözleşmesi, idempotency, config validasyonu) özenle tasarlanmış — ama **görüşmenin kendisini yürüten kod eksik**: agent açılış cümlesini söyler söylemez, karşı tarafı hiç dinlemeden görüşmeyi kendi kendine sonlandırıyor. Bu, "küçük düzeltme" değil, job lifecycle'ının merkezi tasarım eksikliği. Buna ek olarak, bağımsız ve kanıtlanmış bir güvenlik açığı (log redaksiyonunun traceback'i kapsamaması) mevcut. Test sayısı (40 geçti) yüksek görünse de, en kritik testin kendisi (`test_job_handler_success_flow`) bu tasarım eksikliğini "başarı" olarak doğruladığı için, mevcut test paketi bu iki sorunu yakalayacak şekilde tasarlanmamış — düzeltme sonrası test paketi de gözden geçirilmeli, yalnız kod değil.

## 25. Çalıştırılan komutlar

```bash
pwd
git status --short
git diff --stat
git diff --name-only
git log --oneline -5

find . -maxdepth 4 -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/.git/*' -not -path '*/__pycache__/*'

# SDK/dosya doğrulama
cat -n docker-compose.dev.yml / .env.example / services/voice-agent/pyproject.toml
grep -n -A3 'name = "livekit' services/voice-agent/uv.lock
grep -n -A2 'name = "openai"' services/voice-agent/uv.lock

# Gerçek SDK introspection (services/voice-agent/.venv içinde, ağ bağlantısı yok)
.venv/bin/python -c "import livekit.agents as agents; ..."
.venv/bin/python -c "import inspect; from livekit.agents import AgentServer, AgentSession, Agent, room_io; print(inspect.signature(...))"
.venv/bin/python -c "from livekit import api as lk_api; req = lk_api.CreateSIPParticipantRequest(); print([f.name for f in req.DESCRIPTOR.fields])"
.venv/bin/python -c "from livekit.plugins import openai; print(inspect.signature(openai.realtime.RealtimeModel.__init__))"

# Statik doğrulamalar
.venv/bin/python -m compileall -q agent tests
.venv/bin/python -m ruff check agent tests
.venv/bin/python -m mypy agent
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest --cov=agent --cov-report=term-missing -q
.venv/bin/python -m agent.main --check-config

# Docker config doğrulama
docker compose -f docker-compose.dev.yml config -q
docker compose -f docker-compose.dev.yml --profile voice config -q
docker compose -f docker-compose.dev.yml config --services
docker compose -f docker-compose.dev.yml --profile voice config --services

# Güvenlik/redaksiyon araştırması
grep -rn "usage_from_sdk_event\|session.on\|room.on\|wait_for\|asyncio.Event\|close_on_disconnect\|aclose" agent/
grep -rn "print(\|logger\.\|repr(\|model_dump(\|response\.text\|request\.content\|traceback" agent/
grep -rn "LiveKitRealtimeSessionAdapter\|LiveKitSIPParticipantAdapter" tests/

# Log redaksiyon repro (izole, harici bağlantı yok)
.venv/bin/python -c "
from agent.logging import configure_logging
... (bkz. bölüm 14, tam kod)
"

# Kapsam dışı dosya incelemesi
cat PROJECT_STATUS.md TODO.md CHANGELOG.md
tail -40 ~/AI_MEMORY/GLOBAL_STATUS.md
```

Not: `.env` veya secret dosyası açılmadı/oluşturulmadı. Paket kurulumu/güncellemesi yapılmadı (yalnız zaten kurulu `.venv` kullanıldı). Migration çalıştırılmadı. Docker servisi başlatılmadı (yalnız `config` doğrulaması, hiçbir `up` komutu çalıştırılmadı). OpenAI/LiveKit/Netgsm'e hiçbir ağ çağrısı yapılmadı. Git commit/push/reset/checkout/clean/stash yapılmadı.

## 26. Değiştirilen dosyalar

```text
CLAUDE_AUDIT_PHASE_4.md
```
