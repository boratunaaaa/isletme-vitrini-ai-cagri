# Yönetim Paneli (apps/web) — Teknik Dokümantasyon

Bu doküman Aşama 5'te oluşturulan Next.js yönetim panelini açıklar. Panel FastAPI
backend'in gerçek, doğrulanmış contract'ına (`services/api/app/api/routes/**`,
`services/api/app/schemas/**`) karşı yazılmıştır — hiçbir endpoint, HTTP metodu
veya response alanı tahmin edilmemiştir.

> **GÜNCELLEME (bağımsız Codex denetimi sonrası düzeltme turu)** — Codex'in
> `CODEX_AUDIT_PHASE_5_FRONTEND.md`'de bulduğu tek YÜKSEK bulgu (süresi dolmuş
> `ivac_session` çerezinin `/login` ↔ `/` arasında sonsuz redirect loop
> üretebilmesi) ve Playwright'ın `apps/web` içinden çalıştırıldığında Vitest
> dosyalarını E2E testi sanması sorunu düzeltildi. Bu bölümdeki §3 (Auth) ve
> §11 (Test Kapsamı) alt bölümleri bu düzeltmeyi yansıtacak şekilde
> güncellendi (eski içerik SİLİNMEDİ, "DÜZELTME" notlarıyla işaretlendi).
> Tam ayrıntı: `CLAUDE_FIX_PHASE_5_FRONTEND.md`.

## 1. Mimari

```
apps/web/
  app/
    layout.tsx              # Kök layout: QueryClientProvider (lib/providers.tsx)
    globals.css              # Tailwind v4 tema (koyu lacivert + turuncu marka)
    login/page.tsx            # Route group DIŞINDA — SessionProvider gerektirmez
    (app)/                    # Route group — AppShell (sidebar+topbar+SessionProvider) sarmalar
      layout.tsx
      page.tsx                 # Dashboard ("/")
      leads/{page,import/page,[id]/page}.tsx
      campaigns/{page,[id]/page}.tsx
      calls/{page,live/page,[id]/page}.tsx
      callbacks/, demo-requests/, suppression/
      knowledge-base/, prompts/
      pricing/, settings/, audit-logs/, users/
  components/
    layout/  (app-shell, sidebar, topbar, page-header, nav-items)
    ui/      (button, input, data-table, status-badge, stat-card, states,
               pagination, filter-bar, confirm-dialog, masked-phone,
               permission-guard, integration-status-card)
  lib/
    api/     (client.ts, schemas.ts, + bir dosya per domain: auth/leads/
               imports/campaigns/calls/ops/content/system/users)
    auth/session-context.tsx
    hooks/use-live-events.ts   # SSE
    enums.ts, format.ts, cn.ts, providers.tsx
  middleware.ts
  vitest.config.ts, playwright.config.ts (bkz. tests/e2e/)
```

Neden `packages/ui`, `packages/shared-types`, `packages/config` kullanılmadı:
tek bir tüketici (apps/web) olduğu için ayrı paketlere bölmek bu aşamada
gereksiz soyutlama olurdu (erken optimizasyon). Bu paket dizinleri boş
placeholder olarak kaldı; birden fazla frontend tüketicisi olduğunda anlamlı
hale gelecek.

## 2. Backend Contract Envanteri (bu oturumda dosyalar okunarak çıkarıldı)

Gerçek prefix: `/api` (bkz. `services/api/app/main.py`). Tüm mutasyon
isteklerinde `X-CSRF-Token` header'ı zorunludur (double-submit cookie deseni).

| Alan | Router dosyası | Örnek uçlar |
|---|---|---|
| Auth | `routes/auth.py` | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| Leads | `routes/leads.py` | `GET/PATCH /leads`, `/leads/{id}/reveal-phone`, `/leads/{id}/notes`, `/leads/tags/all`, `POST /leads/export` |
| Imports | `routes/lead_import.py` | `POST /imports/preview`, `POST /imports/commit`, `GET /imports` |
| Campaigns | `routes/campaigns.py` | `GET/POST /campaigns`, `/campaigns/{id}/leads`, `/campaigns/{id}/status`, `/campaigns/{id}/stats` |
| Calls | `routes/calls.py` | `POST /calls`, `GET /calls`, `GET /calls/live`, `GET /calls/{id}`, `/calls/{id}/hangup`, `/calls/{id}/quality` |
| Ops | `routes/ops.py` | `/callbacks`, `/demo-requests`, `/demo-requests/{id}/wa-link`, `/suppression` |
| Content | `routes/content.py` | `/kb`, `/prompts`, `/prompts/{id}/activate` |
| Live | `routes/live.py` | `GET /live/events` (SSE) |
| **System** ⚠️ | `routes/system.py` **(bu oturumda eklendi)** | `/dashboard/stats`, `/pricing`, `/settings`, `/audit-logs` |
| Users | `routes/users.py` | `GET/POST /users`, `PATCH/DELETE /users/{id}` |

### 2.1. Bulunan gerçek backend contract eksikliği (raporlanan, minimal düzeltilen)

`app/schemas/system.py` (`DashboardStats`, `PricingOut`, `SettingItem`,
`AuditLogOut`, `IntegrationStatus`), `app/models/system.py`, `app/models/pricing.py`
ve `app/services/settings_service.py` **zaten mevcuttu**, ama hiçbir router
bunları dışarı açmıyordu — Dashboard/Fiyatlandırma/Ayarlar/Audit Log
sayfalarının bağlanacağı gerçek bir uç yoktu. Kullanıcının talimatı
("gerçek bir backend contract eksikliği bulursan doğrula, minimal düzelt,
test et, açıkça raporla") uyarınca:

- Yeni dosya: `services/api/app/api/routes/system.py` — 6 endpoint
  (`GET /dashboard/stats`, `GET/PATCH /pricing[/{id}]`, `GET/PATCH /settings`,
  `GET /audit-logs`), tamamı mevcut `Permission` matrisiyle (`SETTINGS_READ`,
  `PRICING_WRITE`, `SETTINGS_WRITE`, `AUDIT_READ`) korunuyor.
- `app/main.py`'ye `system.router` eklendi.
- 11 yeni entegrasyon testi: `services/api/tests/integration/test_system_api.py`
  (RBAC izin matrisi, Decimal→str serileştirme doğruluğu, invalid decimal 422,
  allowlist dışı ayar reddi, audit yazımı, dashboard maliyet/outcome agregasyonu).
- Voice runtime'a, diğer domain servislerine veya mevcut endpoint'lere
  **dokunulmadı**.
- Sonuç: backend testleri 118 → **129** (hepsi geçiyor), Ruff/MyPy temiz.

Diğer küçük bulgu (düzeltilmedi, yalnız raporlanıyor): `event_bus.py`'nin
yayınladığı SSE olayları asla tam bir `call`/`lead` nesnesi taşımıyor —
yalnız `{type, call_id, status, event_type, ...}` sinyali veriyor
(`app/services/call_service.py`, `app/providers/notification.py`,
`app/api/routes/internal/calls.py` içindeki gerçek `publish_event(...)`
çağrıları okunarak doğrulandı). Panel bunu bir kusur olarak DEĞİL, tasarım
gerçeği olarak ele aldı: `useLiveEvents` SSE payload'ını doğrudan UI state'i
yapmak yerine ilgili React Query anahtarlarını invalidate edip gerçek veriyi
REST'ten tazeliyor (bkz. §5).

## 3. Kimlik Doğrulama ve Oturum

- Backend `Argon2id` + Redis tabanlı opak oturum token'ı kullanır
  (`ivac_session`, httpOnly, `SameSite=Lax`). Panel bu token'ı **hiçbir zaman**
  okumaz/saklamaz — yalnız `credentials: "include"` ile tarayıcının kendisinin
  göndermesine izin verir.
- CSRF: backend `ivac_csrf` adında httpOnly OLMAYAN ikinci bir çerez yazar
  (`csrf_token_for_session`). `lib/api/client.ts::readCsrfCookie()` bunu okuyup
  GET/HEAD dışındaki her istekte `X-CSRF-Token` header'ına koyar
  (`app/deps.py::get_current_user` bunu doğrular).
- `middleware.ts`: yalnız `ivac_session` çerezinin VARLIĞINA bakar (hızlı
  yönlendirme optimizasyonu). Gerçek geçerlilik kontrolü `SessionProvider`
  içindeki `GET /api/auth/me` çağrısıdır — 401 dönerse `/login`'e yönlendirir.
  Bu iki katman kasıtlı: middleware server-side round-trip olmadan bariz
  oturumsuz erişimi engeller, session-context gerçek backend doğrulamasını yapar.
  > **DÜZELTME (Codex YÜKSEK-1, `CLAUDE_FIX_PHASE_5_FRONTEND.md`)**:
  > Middleware önceden çerez VARSA `/login`'den koşulsuz `/`'e yönlendiriyordu
  > — süresi dolmuş ama silinmemiş bir çerezle bu, `SessionProvider`'ın 401
  > sonrası `/login`'e attığı yönlendirmeyle çakışıp sonsuz bir redirect loop
  > üretiyordu. Middleware artık `/login`'den ASLA zorla yönlendirme yapmıyor;
  > geçerli-oturum → dashboard yönlendirmesi artık `app/login/page.tsx`
  > içinde GERÇEK `useMe()` sonucuna göre yapılıyor (bkz. §6). `next` query
  > parametresi `lib/auth/safe-redirect.ts::getSafeRedirectPath()` ile
  > doğrulanıyor (open redirect koruması — yalnız kök-göreli path'lere izin
  > verilir).
  > **2. DÜZELTME (Codex kapanış denetimi YÜKSEK-1,
  > `CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md`)**: İlk `getSafeRedirectPath()`
  > yalnız string prefix kontrolü yapıyordu ve `"/\evil.example"`
  > (slash+backslash) varyantını kaçırıyordu — WHATWG `URL` çözümlemesi bu
  > değeri harici host'a çevirebiliyordu. Helper artık: (1) ham VE decode
  > edilmiş değerde backslash/kontrol karakteri erken reddediyor, (2) en
  > fazla 3 tur sınırlı percent-decode ile çift-encode bypass'ını yakalıyor,
  > (3) sonucu sabit güvenilir bir origin'e göre `new URL()` ile çözüp
  > **origin eşitliği** kanıtlanmadan asla kabul etmiyor (yalnız
  > prefix kontrolüne güvenmiyor).
- RBAC: `lib/auth/session-context.tsx::hasPermission/hasRole`, backend'in
  `MeResponse.permissions` listesini aynen kullanır (`app/core/rbac.py`'deki
  `Permission` string değerleriyle bire bir). `PermissionGuard` bileşeni ve
  sidebar (`nav-items.ts`) bunu UI gizleme için kullanır — **gerçek yetki
  kontrolü her zaman backend'dedir**, bu yalnız UX'tir.

## 4. API İstemcisi

`lib/api/client.ts::apiRequest<T>(path, zodSchema, options)`:

- `NEXT_PUBLIC_API_URL` (varsayılan `http://localhost:8000`) baz alınır.
- Başarılı yanıt Zod şemasıyla **runtime'da doğrulanır** — backend beklenmedik
  bir alan eksik/fazla gönderirse sayfa sessizce yanlış veri göstermek yerine
  hata fırlatır.
- Hata yanıtları backend'in gerçek zarfına göre ayrıştırılır: `{"detail": str}`
  (401/403/404/409/vb.) veya `{"detail": str, "errors": [...]}` (422) —
  `app/main.py`'deki `http_exception_handler`/`validation_exception_handler`
  ile doğrulandı. `ApiError.fieldErrors` 422 `loc` alanlarından form alan
  adlarını çıkarır.
- `lib/api/schemas.ts` her response/request şemasını backend Pydantic
  modeliyle **birebir** eşler (dosya başındaki yorum bu disiplini belirtir).

## 5. Canlı Aramalar (SSE)

`GET /api/live/events` (`app/api/routes/live.py`) Redis pub/sub → SSE.
Gerçek yayınlanan olay şekilleri (üç farklı `publish_event(...)` çağrı yeri
okunarak çıkarıldı — §2.1'e bakınız): `call_event`, `call_completed`,
`internal_call_event`, `notification`. Hiçbiri tam nesne taşımaz.

`lib/hooks/use-live-events.ts`:
- `EventSource(..., {withCredentials:true})`, manuel üstel geri çekilme
  (1s → 30s tavan), `heartbeat` event'inde (backend 20 sn'de bir gönderir)
  deneme sayacını sıfırlar.
- Son N (25) mesajın ham JSON'unu dedup için tutar (reconnect replay'e karşı).
- Olay geldiğinde ilgili React Query anahtarlarını invalidate eder
  (`["calls","live"]`, `["dashboard"]`, `["calls","detail",id]`,
  `["callbacks"]`, `["demo-requests"]`) — SSE yalnız "bir şey değişti" sinyali,
  gerçek veri her zaman REST'ten gelir.
- Yalnız oturum doğrulandıktan sonra bağlanır (`enabled` parametresi).

`/calls/live` sayfası ayrıca 5 saniyelik `refetchInterval` ile polling yapar
(SSE bağlantısı kopsa bile veri tazeliği garanti edilir).

## 6. Tasarım Sistemi

Tailwind v4 (`@theme` bloğu, `app/globals.css`) — koyu lacivert zemin
(`--color-bg-canvas #0b1120`), turuncu marka rengi (`--color-brand-500 #f97316`),
yeşil/sarı/kırmızı/mavi durum renkleri. Sabit koyu tema (uygulama iç
yönetim paneli, kullanıcı tercihi gerektirmiyor).

Paylaşılan bileşenler (`components/ui/`, `components/layout/`): `Button`,
`Input/Select/Textarea/Label`, `DataTable` (TanStack Table), `StatusBadge`
(enum→renk eşlemesi, bilinmeyen değer için nötr fallback — bkz. §7),
`StatCard`, `Pagination`, `FilterBar`, `ConfirmDialog` (Radix Dialog),
`MaskedPhone` (yalnız `phone:reveal` izniyle "göster", her tıklamada backend'i
tazeden çağırır — asla client'ta cache'lenmez), `PermissionGuard`,
`IntegrationStatusCard`, `AppShell`/`Sidebar`/`Topbar`/`PageHeader`.

## 7. Enum/Durum Eşlemesi

`lib/enums.ts` tek doğrulama kaynağı olarak `app/models/enums.py`'yi
referans alır. Her `xMeta(value)` fonksiyonu bilinmeyen bir değer için
**UI'ı ÇÖKERTMEK YERİNE** nötr bir rozet döner (ham değeri göstererek) —
backend enum'u güncellenip panel güncellenmezse sayfa kırılmaz.

## 8. Zaman Dilimi

Backend `APP_TIMEZONE=Europe/Istanbul` kullanır (`config.py`,
`services/call_policy.py::now_istanbul`). `lib/format.ts` tüm
tarih/saat gösterimini `Intl.DateTimeFormat("tr-TR", {timeZone:
"Europe/Istanbul"})` ile yapar; backend timestamp'leri her zaman ISO-8601
(UTC) döner.

## 9. Formlar

React Hook Form + Zod (`@hookform/resolvers/zod`). Zod şemaları backend
Pydantic `Field()` kısıtlarını (min/max length, sayı aralığı, regex pattern)
aynen yansıtır (`lib/api/schemas.ts` mutasyon girdi şemaları). Backend 422
`errors[].loc` alanları `ApiError.fieldErrors`'a haritalanır ama bu oturumda
formlar 422 mesajını genel bir hata bandı olarak gösteriyor (alan-bazlı
otomatik haritalama altyapısı var, her formda ayrı ayrı kablolanmadı — bkz.
§12 bilinen eksikler).

## 10. Güvenlik

- Token/oturum yalnız httpOnly çerezde; localStorage/sessionStorage'da
  hiçbir kimlik bilgisi tutulmaz.
- CSRF header her mutasyonda otomatik eklenir.
- Telefon numaraları backend'den zaten maskeli gelir (`phone_masked`); tam
  numara yalnız `phone:reveal` izniyle, her seferinde backend'i audit'leyen
  ayrı bir çağrıyla (`reveal-phone`) görüntülenir ve React state'i unmount'ta
  düşer.
- CSV export backend'de zaten maskeli üretilir (`POST /leads/export`).
- Tüm mutasyon/silme aksiyonları (`ConfirmDialog`) onay ister.

## 11. Test Kapsamı

- **Vitest + Testing Library**: **33 test** (`lib/format.test.ts`,
  `lib/enums.test.ts`, `lib/api/client.test.ts` — CSRF header davranışı,
  hata ayrıştırma, 401 tespiti dahil —, `components/ui/status-badge.test.tsx`,
  `lib/auth/safe-redirect.test.ts` — **16 test** — kabul edilen dahili
  path'ler, harici URL, protokol-göreli, slash+backslash açık redirect
  varyantı, tek/çift-encode edilmiş varyantlar, tehlikeli şemalar,
  malformed percent-encoding, kontrol karakterleri, yanlış-pozitif
  kontrolü). Detay: `CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md` §9.
- **Playwright** (`tests/e2e/`, paket adı `@ivac/e2e`): **23 test**, **gerçek
  çalışan backend + Postgres + Redis + Next.js dev sunucusuna karşı**
  (mock YOK): oturumsuz yönlendirme, yanlış parola, doğru giriş, çıkış,
  dashboard gerçek metrikler + konsol hatası yokluğu, sidebar gezinme
  (Lead'ler/Kampanyalar/Canlı Aramalar/Kullanıcılar), 375px mobil hamburger
  menü (11 — önceki oturum), + auth redirect regresyon paketi
  (`auth-redirect.spec.ts`, **12 test** — geçerli/geçersiz/yok çerez ×
  `/login`/korumalı-route matrisi, açık redirect koruması (slash+backslash
  ve encoded varyantlar dahil, `CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md` §10),
  redirect-loop regresyon kanıtı). `global-setup.ts` TEK
  bir gerçek UI girişi yapıp `storageState` kaydeder ve çoğu teste enjekte
  eder — backend'in login rate limiter'ını (ip+email başına 60 sn'de 5
  deneme, `app/core/ratelimit.py`) her testte yeniden login yaparak
  tetiklememek için (ilk denemede gerçekten tetiklendi ve 3 test başarısız
  oldu — kök neden analizi ve düzeltmesi `CLAUDE_PROGRESS_PHASE_5_FRONTEND.md`'de
  belgelendi). Yeni `auth-redirect.spec.ts` SIFIR ek gerçek login POST'u
  yapar (paylaşılan storageState + backend'in asla tanımadığı sahte çerez
  enjeksiyonu kullanır) — rate limitin altında kaldı.
  > **DÜZELTME (Codex Playwright discovery bulgusu)**: `cd apps/web && pnpm
  > exec playwright test` önceden `apps/web`'de config bulamayıp Vitest
  > `*.test.ts(x)` dosyalarını E2E testi sanıp çöküyordu. Artık
  > `apps/web/playwright.config.ts` gerçek `tests/e2e/playwright.config.ts`'yi
  > saf veri olarak import edip yalnız yol alanlarını mutlak yola çeviriyor
  > (config kopyalanmadı, yeni bağımlılık eklenmedi). `apps/web/package.json`'a
  > `test:e2e`/`test:e2e:headed`/`test:e2e:list` script'leri eklendi.
  > `pnpm exec playwright test --list` artık yalnız 20 gerçek E2E testini
  > listeliyor. Ayrıntı: `CLAUDE_FIX_PHASE_5_FRONTEND.md` §10-12.
- **Kapsam dışı bırakılan (dürüstçe raporlanıyor, bu düzeltme turunda da
  genişletilmedi — kullanıcı talimatı gereği)**: kullanıcının istediği ~15
  E2E akışının tamamı değil, en yüksek değerli 23 tanesi yazıldı (auth + auth
  redirect matrisi, dashboard, RBAC gezinme, mobil responsive). Lead import
  wizard, kampanya oluşturma/durum geçişi, arama başlatma/sonlandırma,
  suppression CRUD gibi akışlar için E2E hâlâ YAZILMADI (manuel curl ile
  backend contract'ı doğrulandı, sayfalar derleniyor ve tip güvenli, ama
  uçtan uca tarayıcı testi yok).
- **MSW**: bağımlılık olarak eklendi (paket.json) ama entegrasyon testi
  YAZILMADI — yalnız Playwright (gerçek backend) ve birim testleri (mock'suz,
  `vi.stubGlobal("fetch", ...)`) kullanıldı. Kullanıcı spesifikasyonu MSW'yi
  "yalnız entegrasyon testleri için, üretim bağlantısı için değil" diye
  belirtmişti — bu ilke ihlal edilmedi (MSW hiç production kod yoluna
  girmedi), ama MSW'nin kendisi fiilen kullanılmadı.

## 12. Bilinen Eksikler / Kasıtlı Kapsam Dışı Bırakmalar

Kullanıcı talimatı gereği ("fabrikasyon veri gösterme, olmayan özelliği
varmış gibi gösterme") aşağıdakiler **bilerek eksik** bırakıldı, sahte veriyle
doldurulmadı:

- Form alan-bazlı 422 hata haritalama her formda tek tek kablolanmadı (genel
  hata bandı gösteriliyor, altyapı `ApiError.fieldErrors`'da hazır).
  Kampanya/lead formlarında da RHF `setError` ile alan bazlı gösterime
  bağlanabilir; bu oturumda zaman kısıtı nedeniyle yapılmadı.
- `leads/[id]` sayfasında lead'e kullanıcı atama (`assigned_user_id`) alanı
  düzenlenemiyor (kullanıcı listesini çekmek `users:manage` izni ister,
  atama arayüzü ayrı bir seçim bileşeni gerektirir — bu oturumda kapsam dışı
  bırakıldı).
- Recharts bağımlılığı eklendi ama dashboard'da hiçbir grafik ÇİZİLMEDİ
  (yalnız sayısal `StatCard`'lar) — zaman içinde trend grafiği eklenmek
  istenirse bağımlılık zaten mevcut.
- 15 E2E akışın tamamı değil 11'i yazıldı (bkz. §11).
- `packages/ui`/`packages/shared-types`/`packages/config` hâlâ boş
  (bilinçli, §1'e bakınız).

## 13. Yerel Geliştirme

```bash
# 1) Altyapı
docker compose -f docker-compose.dev.yml up -d   # Postgres + Redis

# 2) Backend
cd services/api
uv run alembic upgrade head
uv run python -m app.seed
BOOTSTRAP_ADMIN_EMAIL=you@example.com BOOTSTRAP_ADMIN_PASSWORD='...' uv run python -m app.bootstrap
uv run uvicorn app.main:app --reload --port 8000

# 3) Frontend (ayrı terminal)
cd apps/web
pnpm install
NEXT_PUBLIC_API_URL=http://localhost:8000 pnpm dev   # http://localhost:3000

# 4) Kalite kapıları
pnpm --filter @ivac/web lint
pnpm --filter @ivac/web typecheck
pnpm --filter @ivac/web test
pnpm --filter @ivac/web build

# 5) E2E (backend + frontend zaten ayakta olmalı)
E2E_OWNER_EMAIL=you@example.com E2E_OWNER_PASSWORD='...' pnpm --filter @ivac/e2e test
```
