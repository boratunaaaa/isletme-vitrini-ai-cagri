# CHANGELOG.md

## Değişiklik Geçmişi

### 2026-07-18 — Aşama 5, Frontend Kapanış Denetimi Düzeltmesi: Open Redirect (Backslash Varyantı)

**Aşağıdaki "Stale-Cookie Login Loop + Playwright Config Ayrımı" girdisini
tamamlar** — bağımsız bir Codex kapanış denetimi (`CODEX_FINAL_AUDIT_PHASE_5_FRONTEND.md`,
karar: `KÜÇÜK DÜZELTMELERDEN SONRA COMMIT EDİLEBİLİR`) o girdideki
stale-cookie ve Playwright discovery düzeltmelerinin tam kapandığını
doğruladı, ama `getSafeRedirectPath()`'te yeni bir YÜKSEK bulgu buldu. Bu
girdi yalnız o bulguyu kapatır (detay: `CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md`):

- **Backslash open-redirect varyantı düzeltildi (YÜKSEK-1)** — helper
  yalnız `startsWith("/")`/`startsWith("//")`/`includes("://")` string
  kontrolüne dayanıyordu ve `"/\evil.example"` (slash+backslash) değerini
  kabul ediyordu; WHATWG URL çözümlemesi bunu harici host'a
  çevirebiliyordu (`new URL('/\evil.com', origin).href` → `http://evil.com/`,
  yerel olarak doğrulandı). Düzeltme: `getSafeRedirectPath()` artık (1) ham
  VE decode edilmiş değerde backslash/kontrol karakteri erken reddediyor,
  (2) en fazla 3 tur sınırlı `decodeURIComponent` ile çift-encode bypass'ını
  (`%252F%252F...` gibi) yakalıyor, (3) sonucu sabit güvenilir bir origin'e
  göre `new URL()` ile çözüp **origin eşitliği** kanıtlanmadan asla kabul
  etmiyor — artık yalnız string prefix kontrolüne güvenmiyor.
- Kullanım noktaları (`grep -rn "getSafeRedirectPath"` + `router.push`/
  `replace`/`redirect(`/`window.location` taraması) doğrulandı: helper'ın
  tek çağrı yeri `app/login/page.tsx`'in iki noktası, ikisi de zaten
  helper üzerinden geçiyordu — kod değişikliği gerekmedi.
- Vitest `safe-redirect.test.ts` 5→**16** teste genişletildi (backslash,
  tek/çift-encode, kontrol karakteri, malformed percent-encoding,
  yanlış-pozitif kontrolü — `/@evil.example` gibi zararsız path'lerin
  yanlışlıkla reddedilmediği de doğrulandı). Playwright `auth-redirect.spec.ts`'e
  3 yeni test eklendi (10d/10e/10f — `%2F%5Cevil.example`,
  `%2F%2Fevil.example`, `https%3A%2F%2Fevil.example`), sıfır ek gerçek
  login POST'uyla (rate limiter'a dokunulmadı).
- Doğrulama: Vitest 22→**33 passed**, Playwright 20→**23 passed** (gerçek
  backend+Postgres+Redis+Next.js'e karşı, gerçekten çalıştırıldı),
  lint/typecheck/build (apps/web + kök workspace) temiz. Backend hiç
  değiştirilmedi (yalnız okundu, diff aynı kaldı).
- Nihai karar: **`FRONTEND COMMIT İÇİN HAZIR`**.

### 2026-07-18 — Aşama 5, Codex Denetim Düzeltmesi: Stale-Cookie Login Loop + Playwright Config Ayrımı

**Aşağıdaki "Aşama 5: Next.js Yönetim Paneli" girdisini düzeltir** — bağımsız
bir Codex denetimi (`CODEX_AUDIT_PHASE_5_FRONTEND.md`, karar: `KÜÇÜK
DÜZELTMELERDEN SONRA COMMIT EDİLEBİLİR`) o girdinin tamamlandığı andaki
koddan bir YÜKSEK bulgu buldu ve E2E'nin kendi ortamında (backend ayakta
değildi) koşamadığını bildirdi. Bu girdi yalnız o iki alanı kapatır (detay:
`CLAUDE_FIX_PHASE_5_FRONTEND.md`):

- **Stale-cookie login redirect loop düzeltildi (YÜKSEK-1)** — kök neden
  kod okunarak doğrulandı: `middleware.ts` çerezin yalnız VARLIĞINA bakıp
  `/login`'den koşulsuz `/`'e yönlendiriyordu; süresi dolmuş bir çerezle
  `SessionProvider`'ın 401-sonrası `/login`'e attığı yönlendirmeyle
  çakışıp sonsuz döngü oluşuyordu. Düzeltme: middleware artık `/login`'den
  ASLA zorla yönlendirmiyor; geçerli-oturum → dashboard yönlendirmesi
  `app/login/page.tsx`'e taşındı ve GERÇEK `useMe()` (`/api/auth/me`)
  sonucuna dayanıyor. Yeni `lib/auth/safe-redirect.ts::getSafeRedirectPath()`
  `/login?next=...` için open-redirect koruması ekliyor (yalnız kök-göreli
  path'lere izin verir). 9 yeni E2E testi (`auth-redirect.spec.ts`) bunu
  gerçek production middleware+auth provider yolunda doğruluyor — sıfır ek
  gerçek login POST'uyla (rate limiter'a dokunulmadı).
- **Playwright/Vitest test discovery ayrıldı** — doğrulandı: `cd apps/web
  && pnpm exec playwright test` config bulamayıp Vitest `*.test.ts(x)`
  dosyalarını E2E testi sanıp çöküyordu. Yeni `apps/web/playwright.config.ts`
  gerçek `tests/e2e/playwright.config.ts`'yi SAF VERİ olarak import edip
  yalnız yol-duyarlı alanları mutlak yola çeviriyor — config kopyalanmadı,
  `apps/web`'e yeni bir bağımlılık eklenmedi. `apps/web/package.json`'a
  `test:e2e`/`test:e2e:headed`/`test:e2e:list` eklendi. `--list` ile
  doğrulandı: artık yalnız 20 gerçek E2E testi görünüyor.
- Doğrulama: Vitest 17→**22 passed**, Playwright 11→**20 passed** (gerçek
  backend+Postgres+Redis+Next.js'e karşı, bu kez gerçekten çalıştırıldı),
  lint/typecheck/build (apps/web + kök workspace) temiz, backend regresyonu
  (dokunulmadı ama doğrulandı) **129 passed**, Docker config geçti.
- Backend auth/rate-limit koduna dokunulmadı (yalnız okundu). Yeni özellik
  eklenmedi, kapsam genişletilmedi. Commit/push yapılmadı.
- Nihai karar: **`FRONTEND COMMIT İÇİN HAZIR`**.

### 2026-07-18 — Aşama 5: Next.js Yönetim Paneli (`apps/web`)

Baseline commit `03bfa9e` üzerine gerçek backend contract'ına bağlı bir
yönetim paneli eklendi. Ayrıntılı rapor: `CLAUDE_PROGRESS_PHASE_5_FRONTEND.md`,
teknik doküman: `docs/frontend-management-panel.md`.

- **Backend'de bulunan gerçek contract eksikliği kapatıldı**: `app/schemas/system.py`
  (Dashboard/Pricing/Settings/AuditLog şemaları) ve ilgili modeller/servisler
  mevcuttu ama hiçbir router dışarı açmıyordu. Yeni `app/api/routes/system.py`
  (6 endpoint, mevcut RBAC matrisiyle korunuyor) + `app/main.py`'ye mount +
  11 yeni entegrasyon testi (`test_system_api.py`). Backend testleri
  118 → **129 passed**, Ruff/MyPy temiz. Voice-agent'a ve diğer route'lara
  dokunulmadı.
- **`apps/web`**: Next.js 15 + React 19 + Tailwind 4 + TanStack Query/Table +
  Zod + React Hook Form + Radix UI. 20 sayfa (dashboard, lead yönetimi + toplu
  içe aktarma, kampanya yönetimi, arama geçmişi + canlı aramalar (SSE) + arama
  detayı, geri arama/demo talebi/arama engeli operasyonları, bilgi bankası/
  prompt versiyonları, fiyatlandırma/ayarlar/audit log/kullanıcı yönetimi).
  Auth tamamen backend'in httpOnly session çerezi + CSRF double-submit
  deseniyle (hiçbir token client'ta saklanmıyor); RBAC UI-gating backend'in
  `permissions[]` listesini birebir kullanıyor (gerçek kontrol her zaman
  backend'de). SSE canlı olayları doğrudan UI state'i yapmak yerine React
  Query invalidation tetikleyicisi olarak kullanılıyor (backend'in
  `publish_event()` çağrı yerleri okunarak olay şeklinin asla tam nesne
  taşımadığı doğrulandı).
- **Kalite kapıları**: `pnpm lint`/`typecheck`/`build` temiz, Vitest 17/17,
  yeni `@ivac/e2e` (Playwright) paketiyle 11/11 E2E testi **gerçek çalışan
  backend+Postgres+Redis+Next.js dev sunucusuna karşı** (mock yok) geçti.
  E2E ilk çalıştırmasında gerçek bir bulgu ortaya çıktı: backend'in login
  rate limiter'ı (ip+email başına 60 sn'de 5 deneme) testlerin her birinin
  taze UI login'i yapması yüzünden tetiklendi — rate limiter ZAYIFLATILMADI,
  bunun yerine Playwright `storageState` paylaşımına geçilerek test
  stratejisi düzeltildi.
- Bilinçli olarak eksik bırakılanlar (fabrikasyon veri/sahte "tamamlandı"
  iddiası yok, hepsi `CLAUDE_PROGRESS_PHASE_5_FRONTEND.md` §25'te listeli):
  form alan-bazlı 422 hata haritalama her formda kablolanmadı, ~15 E2E
  akışının 11'i yazıldı, tarayıcı uzantısı bu oturumda bağlı olmadığı için
  manuel doğrulama yerine Playwright/curl kullanıldı, 320/768/1440px
  responsive testleri otomatikleştirilmedi.
- Commit/push yapılmadı (kullanıcı onayı bekliyor).

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
