# 1. Yönetici özeti

Karar: `KÜÇÜK DÜZELTMELERDEN SONRA COMMIT EDİLEBİLİR`.

Next.js yönetim paneli genel olarak gerçek FastAPI contract'larına bağlı. Auth cookie modeli, CSRF header akışı, Zod response validation, temel RBAC görünürlük kontrolleri ve yeni backend `system` router'ı gerçek production code path üzerinde kurulmuş. Sahte başarı üreten ana sayfa tespit etmedim.

Commit öncesi bir yüksek bulgu var: süresi dolmuş ama tarayıcıda kalmış `ivac_session` cookie'si `/login` ile `/` arasında kullanıcıyı login loop'a sokabilir. Bu küçük kapsamlı bir middleware/auth düzeltmesiyle kapanır. Playwright E2E bu ortamda yeniden geçirilemedi; yerel backend 8000 portunda çalışmadığı için global setup login sonrası `/login` üzerinde kaldı.

# 2. Denetlenen kapsam

Okunan ana kapsam:

- `CLAUDE_PROGRESS_PHASE_5_FRONTEND.md`
- `docs/frontend-management-panel.md`
- `PROJECT_STATUS.md`, `TODO.md`, `CHANGELOG.md`, `BASELINE_SECURITY_AUDIT.md`
- `services/api/app/main.py`
- `services/api/app/api/routes/**`
- `services/api/app/schemas/**`
- `services/api/app/core/security.py`, `ratelimit.py`, `rbac.py`
- `apps/web/**`
- `tests/e2e/**`
- `package.json`, `pnpm-workspace.yaml`, `turbo.json`

# 3. Git ve değişiklik durumu

Başlangıç çalışma klasörü: `/Users/kadirugur/Projects/isletme-vitrini-ai-cagri`.

Son `git status --short`:

```text
 M .env.example
 M .gitignore
 M CHANGELOG.md
 M Makefile
 M PROJECT_STATUS.md
 M TODO.md
 M pnpm-workspace.yaml
 M services/api/app/main.py
?? CLAUDE_PROGRESS_PHASE_5_FRONTEND.md
?? apps/
?? docs/frontend-management-panel.md
?? pnpm-lock.yaml
?? services/api/app/api/routes/system.py
?? services/api/tests/integration/test_system_api.py
?? tests/
```

Tracked diff stat: 8 dosya, 93 ekleme, 4 silme. Frontend aşamasındaki backend production değişikliği `services/api/app/main.py` içine `system` router import/mount eklenmesi ve untracked `services/api/app/api/routes/system.py` dosyasıdır. Bu değişiklik panelin dashboard/pricing/settings/audit-log contract eksikliğini kapatmak için gerekli ve minimum kapsamlı görünüyor. Migration gerektiren schema/model değişikliği tespit etmedim.

Ignored artefact'ler var ve ignore altında: `apps/web/.next/`, `apps/web/node_modules/`, `apps/web/test-results/`, `apps/web/tsconfig.tsbuildinfo`, `tests/e2e/.auth/`, `tests/e2e/test-results/`, `.turbo/`, cache klasörleri.

# 4. Frontend mimarisi

Uygulama `apps/web` altında Next.js App Router, React Query, Zod, React Hook Form ve Radix UI bileşenleriyle kurulmuş. API erişimi tek typed client çevresinde toplanmış: `apps/web/lib/api/client.ts:94-137`.

Build route listesi şu gerçek sayfaları doğruladı:

- `/`
- `/audit-logs`
- `/callbacks`
- `/calls`
- `/calls/[id]`
- `/calls/live`
- `/campaigns`
- `/campaigns/[id]`
- `/demo-requests`
- `/knowledge-base`
- `/leads`
- `/leads/[id]`
- `/leads/import`
- `/login`
- `/pricing`
- `/prompts`
- `/settings`
- `/suppression`
- `/users`

İstenen listede geçen `/dashboard`, `/campaigns/new`, `/calls/history`, `/integrations` ayrı route olarak yok. İşlevler sırasıyla `/`, kampanya create dialog'u, `/calls`, ve `/settings` içinde karşılanıyor.

# 5. Backend contract uyumu

Frontend API modülleri backend route'larıyla genel olarak uyumlu:

- Auth: `/api/auth/login`, `/api/auth/logout`, `/api/auth/me`
- Leads: `/api/leads`, `/api/leads/facets`, `/api/leads/{id}`, `/api/leads/{id}/reveal-phone`, notes/tags/export
- Import: `/api/imports/preview`, `/api/imports/commit`, `/api/imports`
- Campaigns: `/api/campaigns`, `/api/campaigns/{id}`, `/api/campaigns/{id}/leads`, `/status`, `/stats`
- Calls: `/api/calls`, `/api/calls/live`, `/api/calls/{id}`, `/hangup`, `/quality`
- Ops: callbacks, demo requests, suppression
- Content: knowledge base, prompts
- Live: `/api/live/events`
- System: `/api/dashboard/stats`, `/api/pricing`, `/api/settings`, `/api/audit-logs`
- Users: `/api/users`, `/api/users/{id}`

Zod response validation kullanılıyor; backend response doğrulaması bozulursa UI sahte boş veri üretmek yerine query error state'e düşer. Backend'de olmayan endpoint uydurulmuş kritik örnek bulmadım.

# 6. Authentication ve session

Login formu gerçek backend login endpointine gidiyor: `apps/web/app/login/page.tsx:26-30`, `apps/web/lib/api/auth.ts:25-33`. Backend login cookie ve CSRF cookie set ediyor: `services/api/app/api/routes/auth.py:38-58`, `61-104`.

Session token localStorage/sessionStorage'a yazılmıyor. Auth state `/api/auth/me` üzerinden doğrulanıyor ve `useMe` retry kapalı: `apps/web/lib/api/auth.ts:15-22`.

Yüksek bulgu: `apps/web/middleware.ts:26-28` yalnız cookie varlığına bakarak `/login` isteğini `/` adresine yönlendiriyor. Aynı dosyanın yorumları `middleware.ts:4-10` cookie'nin geçerliliğinin doğrulanmadığını açıkça söylüyor. `SessionProvider` 401 alınca `/login` yönlendirmesi yapıyor: `apps/web/lib/auth/session-context.tsx:28-31`. Süresi dolmuş ama silinmemiş cookie durumunda kullanıcı `/login -> / -> /login` döngüsüne girebilir ve tekrar giriş formuna ulaşamayabilir.

# 7. CSRF

CSRF double-submit modeli tutarlı:

- Backend `ivac_session` cookie'sini httpOnly, `ivac_csrf` cookie'sini client-readable set ediyor: `services/api/app/api/routes/auth.py:41-58`.
- API client mutasyonlarda `X-CSRF-Token` header'ı ekliyor: `apps/web/lib/api/client.ts:110-113`, raw response path için `151-154`.
- `credentials: "include"` her iki client path'inde mevcut: `apps/web/lib/api/client.ts:115-120`, `155-160`.

GET isteklerinde CSRF header gönderilmemesi doğru. Logout POST olduğu için CSRF header path'ine giriyor.

# 8. Playwright storageState çözümü

`tests/e2e/global-setup.ts:22-34` gerçek UI login yapıp `tests/e2e/.auth/owner.json` storageState dosyasını yazıyor. `.gitignore` bu klasörü ignore ediyor.

Rate limiter production kodunda gevşetilmemiş; backend login rate limiter `services/api/app/api/routes/auth.py:68-77` üzerinde duruyor. Playwright config backend'i başlatmadığını dokümante ediyor: `tests/e2e/playwright.config.ts:3-15`.

Riskler:

- E2E suite tek owner session ile çalışıyor; viewer/sales_agent role E2E kapsamı yok.
- `fullyParallel: false`, `workers: 1`: paralel state çakışması yok, ancak suite paralellik kanıtı üretmiyor.
- Bu denetimde `pnpm --filter @ivac/e2e test` çalıştı fakat backend 8000 portunda olmadığı için global setup login sonrası `/login` üzerinde kaldı.
- İstenen `cd apps/web && pnpm exec playwright test` komutu gerçek E2E config'i değil, web paketindeki Vitest dosyalarını Playwright gibi yüklemeye çalışıp `Vitest failed to access its internal state` ve `No tests found` ile başarısız oldu.

# 9. API client

Güçlü taraflar:

- `credentials: "include"` var.
- CSRF header mutasyonlarda ekleniyor.
- `AbortSignal` destekleniyor.
- JSON response Zod ile parse ediliyor.
- JSON olmayan error response için fallback var.
- `204` response path'i var.

Eksikler:

- Timeout yok.
- `X-Request-ID` üretilmiyor.
- Retry/backoff politikası yok.
- 401/403/409/422/429/5xx ayrımı yalnız `ApiError.status` üzerinden tüketiciye bırakılmış.
- `apiRequestRaw` `signal` parametresini fetch'e taşımıyor.

Bu eksikler staging smoke testini engellemez, fakat panel operasyonel dayanıklılığı için orta önemde takip edilmeli.

# 10. RBAC

UI görünürlük kontrolü `PermissionGuard` ile yapılıyor ve kendi yorumunda güvenliğin backend'de kaldığı açık: `apps/web/components/ui/permission-guard.tsx:6-10`. Nav item permission mapping'i `apps/web/components/layout/nav-items.ts:32-70` içinde tanımlı.

Backend tarafında sensitive system endpointleri `require_permission` kullanıyor; örnekler `services/api/app/api/routes/system.py:177-195`, `224-253`. Viewer/sales-agent doğrudan URL testleri E2E'de yok; ancak backend 403 güvenliği UI gizlemesine bağlı değil.

# 11. Dashboard ve metrik doğruluğu

Dashboard gerçek aggregate endpoint kullanıyor: `apps/web/app/(app)/page.tsx:22-24`, backend `services/api/app/api/routes/system.py:67-157`.

Metrikler pagination'dan türetilmiyor. Tarih sınırı backend `APP_TIMEZONE` ile local gün başlangıcından UTC'ye çevriliyor: `system.py:60-64`. Maliyetler Decimal değerlerden string olarak taşınıyor: `system.py:103-112`, `140-142`.

Not: `success_rate` yalnız `interested_count / calls_today` olarak hesaplanıyor: `system.py:82-87`. Ürün dilinde "Başarı Oranı" bundan farklı bir satış metriği anlamına gelecekse isim/tooltip netleştirilmeli.

# 12. Lead yönetimi ve import

Lead liste, detay, filtre, pagination ve phone reveal endpointleri gerçek backend route'larına bağlı. Tam telefonun localStorage/sessionStorage'a yazıldığı bir yer bulmadım.

Import akışı preview ve commit'i ayrı endpointlerle yapıyor: `apps/web/lib/api/imports.ts:19-30`, `33-58`. Sayfa file upload ve kolon mapping sunuyor: `apps/web/app/(app)/leads/import/page.tsx:37-47`, `93-173`.

Orta bulgu: API hook'ları `sheetName` destekliyor, fakat import sayfasında `preview.sheet_names` için sheet seçimi UI'da kullanılmıyor; preview ve commit çağrıları `sheetName` taşımıyor (`leads/import/page.tsx:41`, `164`). Çok sayfalı XLSX dosyalarında kullanıcı doğru sheet'i seçemeyebilir.

# 13. Kampanya ve çağrı güvenliği

Kampanya create/update/status akışları gerçek backend contract'larına bağlı. Kampanya oluşturma ayrı `/campaigns/new` route'u yerine `/campaigns` üzerindeki Radix dialog ile yapılıyor: `apps/web/app/(app)/campaigns/page.tsx:24-119`, `154-180`.

Canlı çağrı UI'ı `/api/calls/live` ve SSE invalidation ile bağlı. Test sırasında gerçek telephony/OpenAI/LiveKit çağrısı başlatan kod yolu çalıştırılmadı. Çağrı başlatma güvenliği backend policy'de kalıyor; frontend'in yerel tahminle gerçek aramaya izin verdiği bir path tespit etmedim.

# 14. SSE ve canlı aramalar

SSE hook gerçek `EventSource` ile `/api/live/events` adresine cookie dahil bağlanıyor: `apps/web/lib/hooks/use-live-events.ts:76-80`. GET olduğu için CSRF header gerekmez. Parse hatasında UI çökmüyor; invalid event sessizce yok sayılıyor: `use-live-events.ts:47-60`. Component unmount'ta timer ve source kapanıyor: `96-101`.

Düşük/orta risk: dedupe `event.id` yerine raw JSON metnine dayanıyor: `use-live-events.ts:54-57`. Out-of-order event veya aynı event'in farklı serialization ile gelmesi durumunda ikinci kez işlenebilir. Mevcut payload sadece query invalidation tetiklediği için etkisi düşük.

# 15. Diğer yönetim sayfaları

Sayfa matrisi:

- `/dashboard`: Eksik ayrı route; dashboard `/` üzerinde gerçek backend'e bağlı.
- `/leads`: Tam ve gerçek backend'e bağlı.
- `/leads/import`: Kısmen bağlı; sheet seçimi eksik.
- `/leads/[id]`: Tam ve gerçek backend'e bağlı.
- `/campaigns`: Tam ve gerçek backend'e bağlı.
- `/campaigns/new`: Eksik ayrı route; create dialog `/campaigns` içinde.
- `/campaigns/[id]`: Tam ve gerçek backend'e bağlı.
- `/calls/live`: Tam ve gerçek backend'e bağlı.
- `/calls/history`: Eksik ayrı route; history `/calls` içinde.
- `/calls/[id]`: Kısmen bağlı; transcript raw JSON render ediliyor.
- `/callbacks`: Tam ve gerçek backend'e bağlı.
- `/demo-requests`: Tam ve gerçek backend'e bağlı.
- `/suppression`: Tam ve gerçek backend'e bağlı.
- `/knowledge-base`: Tam ve gerçek backend'e bağlı.
- `/prompts`: Tam ve gerçek backend'e bağlı.
- `/pricing`: Tam ve gerçek backend'e bağlı.
- `/integrations`: Eksik ayrı route; integrations `/settings` ve dashboard içinde.
- `/users`: Tam ve gerçek backend'e bağlı.
- `/audit-logs`: Tam ve gerçek backend'e bağlı.
- `/settings`: Tam ve gerçek backend'e bağlı.

# 16. PII ve frontend güvenliği

Production frontend içinde `localStorage` veya `sessionStorage` kullanımı bulmadım. Token browser storage'a persist edilmiyor. `NEXT_PUBLIC_` tarafında yalnız API base URL kullanımı görüldü.

`console.log`/`console.error` ile tam telefon, transcript veya token basan production path tespit etmedim.

Düşük bulgu: call detail transcript'i raw JSON olarak render ediyor: `apps/web/app/(app)/calls/[id]/page.tsx:103-109`. Backend redaction ana katman olsa da UI yalnız whitelist alanları göstermeli; gelecekte backend response'una hassas ek alan girerse raw dump bunu gösterebilir.

# 17. Accessibility

Olumlu noktalar:

- Form label'ları genel olarak `htmlFor` ile bağlı.
- Login form error `role="alert"` kullanıyor: `apps/web/app/login/page.tsx:79-82`.
- Dialog'lar Radix Dialog ile kurulmuş.
- Nav landmark var: `apps/web/components/layout/sidebar.tsx:27`.
- Mobile menu aç/kapat butonlarında accessible name var.

Eksikler:

- Bazı icon-only action button'larında `aria-label` yok; örnek suppression remove `apps/web/app/(app)/suppression/page.tsx:67-70`, user deactivate `apps/web/app/(app)/users/page.tsx:148-152`.
- Mobile sidebar plain overlay olarak uygulanmış; `role="dialog"`, focus trap ve Escape kapatma garantisi yok: `apps/web/components/layout/sidebar.tsx:77-93`.
- Skip link ve sistematik axe/accessibility testi yok.

# 18. Responsive tasarım

Table'larda genel olarak yatay overflow/min-width kullanımı var; import preview örneği `leads/import/page.tsx:123-145`. Mobile sidebar 375px E2E smoke test ile kapsanmış: `tests/e2e/specs/navigation.spec.ts:33-43`.

Eksik: 320px/375px geniş kapsamlı breakpoint testi, uzun işletme adı/email/Türkçe metin taşması ve chart/table overflow senaryoları henüz testli değil. Koddan açık, kritik bir mobile kırılma tespit etmedim; risk ertelenebilir.

# 19. Unit/integration testleri

`apps/web` unit test sonucu: 4 dosya, 17 test geçti.

Kapsam:

- API client: 6 test
- Enum mapping: 2 test
- Format helpers: 8 test
- Status badge: 1 test

Eksikler:

- Auth/CSRF component-level testleri sınırlı.
- RBAC role matrix unit testleri yok.
- Forms, lead import, campaign mutation, SSE, sensitive data, responsive ve accessibility için unit/integration coverage düşük.
- 409/422/429/5xx UI davranışları kapsamlı testli değil.

# 20. Playwright E2E kapsamı

E2E spec dosyaları:

- `tests/e2e/specs/auth.spec.ts`
- `tests/e2e/specs/dashboard.spec.ts`
- `tests/e2e/specs/navigation.spec.ts`

Kapsanan akışlar: login/logout, yanlış parola, oturumsuz redirect, dashboard smoke, temel navigation, live calls empty state, users owner erişimi, mobile sidebar smoke.

Eksik kritik akışlar: phone reveal, import final confirmation, campaign status transition, call detail, callback update, demo request update, suppression removal, pricing update, prompt activation, session expiry, 403 forbidden, SSE reconnect ve mobile overflow. Bunlar commit'i tamamen engellemez, ancak staging öncesi test planına yazılmalı.

# 21. Backend değişikliği

Frontend aşamasında backend değişikliği `system` router eklenmesi ve `main.py` içinde mount edilmesi. `services/api/app/api/routes/system.py:1-8` bu gerekçeyi açıkça belgeliyor; `services/api/app/main.py:18-29` route importunu ve `system` mount'unu ekliyor.

Yeni router mevcut modelleri dışarı açıyor, migration gerektirmiyor. RBAC dependency'leri pricing/settings/audit için kullanılıyor. Rate limiter production davranışı zayıflatılmamış.

Backend doğrulama bu ortamda geçti: `129 passed, 3 warnings`.

# 22. Kritik bulgular

Kritik bulgu yok.

# 23. Yüksek bulgular

## YÜKSEK-1: Süresi dolmuş session cookie login loop oluşturabilir

Dosya/satır:

- `apps/web/middleware.ts:26-28`
- `apps/web/lib/auth/session-context.tsx:28-31`

Sorun: Middleware `/login` isteğini yalnız `ivac_session` cookie varlığına bakarak `/` adresine çeviriyor. Cookie Redis'te süresi dolmuşsa `useMe()` 401 alıp `/login` yönlendiriyor; middleware cookie hâlâ durduğu için yeniden `/` yönlendiriyor.

Gerçek etkisi: Session expiry yaşayan kullanıcı login formuna ulaşamayabilir. Cookie temizlenene kadar panel erişimi kilitlenir.

Commit'i engeller mi: Evet, küçük bir auth/middleware düzeltmesi gerekiyor.

Staging'i engeller mi: Kontrollü staging smoke'a geçmeden önce düzeltilmeli; aksi halde expiry testi başarısız olur.

Önerilen düzeltme: `/login` path'inde cookie var diye otomatik `/` redirect yapma; login sayfasını render et veya backend session doğrulaması/clear-cookie recovery path'i ekle. En uygun uygulayıcı: Codex veya Claude Sonnet.

# 24. Orta ve düşük bulgular

## ORTA-1: API client timeout/request-id/retry politikası eksik

Dosya/satır: `apps/web/lib/api/client.ts:94-137`, `140-167`.

Etkisi: Network donması, 429/5xx geçici hatalar ve observability için zayıf davranış. Staging'i tek başına engellemez.

Öneri: Timeout wrapper, `X-Request-ID`, sınırlı retry/backoff ve status bazlı error mapping ekle.

## ORTA-2: XLSX sheet seçimi UI'da kullanılmıyor

Dosya/satır: `apps/web/lib/api/imports.ts:21-25`, `39-49`; `apps/web/app/(app)/leads/import/page.tsx:37-47`, `160-165`.

Etkisi: Çok sheet'li dosyalarda doğru sheet seçilemeyebilir. Staging'i engellemez, import staging senaryosundan önce düzeltilmeli.

## ORTA-3: İstenen bazı route'lar ayrı path olarak yok

Kanıt: build route listesinde `/dashboard`, `/campaigns/new`, `/calls/history`, `/integrations` yok. Karşılık gelen işlevler farklı path'lerde mevcut.

Etkisi: Dokümantasyon/UX ve deep-link beklentisi uyuşmazlığı. Staging'i engellemez, ama route alias veya dokümantasyon netliği gerekir.

## DÜŞÜK-1: Call transcript raw JSON render ediliyor

Dosya/satır: `apps/web/app/(app)/calls/[id]/page.tsx:103-109`.

Etkisi: Redacted backend response varsayımı korunursa düşük; gelecekte beklenmeyen alanlar UI'da görünür olabilir.

## DÜŞÜK-2: Icon-only action button'larında accessible name eksikleri var

Dosya/satır: `apps/web/app/(app)/suppression/page.tsx:67-70`, `apps/web/app/(app)/users/page.tsx:148-152`.

Etkisi: Screen reader ve keyboard kullanıcıları için eylem adı belirsiz.

## DÜŞÜK-3: Mobile sidebar focus trap/Escape davranışı garanti değil

Dosya/satır: `apps/web/components/layout/sidebar.tsx:77-93`.

Etkisi: Erişilebilirlik kalitesi düşer; staging'i engellemez.

## DÜŞÜK-4: SSE dedupe raw JSON metnine dayanıyor

Dosya/satır: `apps/web/lib/hooks/use-live-events.ts:54-57`.

Etkisi: Aynı event farklı serialization ile gelirse ikinci invalidation olabilir. Şu an payload yalnız query invalidation yaptığı için düşük etkili.

# 25. Commit öncesi zorunlu düzeltmeler

1. `middleware.ts` login loop bulgusunu düzelt.
2. Backend/Postgres/Redis/bootstrap önkoşulları hazırlanmış lokal veya staging ortamında `pnpm --filter @ivac/e2e test` komutunu yeniden çalıştır ve 11/11 sonucu doğrula.

# 26. Ertelenebilecek iyileştirmeler

- Field-level 422 mapping'i kritik formlara bağla.
- E2E kapsamına phone reveal, import commit, campaign status, call detail, callback/demo/suppression/pricing/prompt flows ekle.
- Responsive 320/375px ve accessibility testleri ekle.
- API client timeout/request-id/retry davranışını güçlendir.
- `/dashboard`, `/calls/history`, `/integrations`, `/campaigns/new` için route alias veya dokümantasyon netliği sağla.

# 27. Sonuç kararı

`KÜÇÜK DÜZELTMELERDEN SONRA COMMIT EDİLEBİLİR`.

Gerekçe: Yeni kritik bulgu yok. Backend contract bağlantıları gerçek ve backend regresyonu geçti. Ancak yeni yüksek auth/session bulgusu var ve Playwright 11/11 sonucu bu ortamda yeniden doğrulanamadı; backend 8000 portunda çalışmadığı için E2E global setup login aşamasında kaldı.

# 28. Çalıştırılan komutlar

```text
pwd
git status --short
git diff --stat
git diff --name-only
git diff -- services/api
git diff -- apps/web packages docs PROJECT_STATUS.md TODO.md CHANGELOG.md
git log -3 --oneline
git status --ignored --short
rg ... frontend sensitive patterns
find ... route/test/large-file inventory
cd apps/web && pnpm lint
cd apps/web && pnpm typecheck
cd apps/web && pnpm test
cd apps/web && pnpm build
cd apps/web && pnpm exec playwright test
pnpm --filter @ivac/e2e test
pnpm lint
pnpm typecheck
pnpm test
pnpm build
cd services/api && uv run ruff check app tests
cd services/api && uv run mypy app
cd services/api && uv run pytest -q
docker compose -f docker-compose.dev.yml config
docker compose -f docker-compose.dev.yml --profile voice config
```

Sonuç özeti:

- `apps/web pnpm lint`: geçti.
- `apps/web pnpm typecheck`: geçti.
- `apps/web pnpm test`: geçti, 17/17.
- `apps/web pnpm build`: geçti.
- `apps/web pnpm exec playwright test`: başarısız; yanlış cwd/config etkisiyle Vitest dosyaları Playwright gibi yüklendi ve `No tests found`.
- `pnpm --filter @ivac/e2e test`: başarısız; backend 8000 portunda çalışmadığı için global setup login sonrası `/login` üzerinde kaldı.
- `pnpm lint`: geçti.
- `pnpm typecheck`: geçti.
- `pnpm test`: unit kısmı geçti, E2E global setup nedeniyle genel komut başarısız.
- `pnpm build`: geçti.
- Backend ruff: geçti.
- Backend mypy: geçti.
- Backend pytest: `129 passed, 3 warnings`.
- Docker compose config: geçti.
- Docker compose `--profile voice` config: geçti.

Not: `pnpm` komutları sandbox içinde registry signature doğrulamasına takıldı; kullanıcı onaylı escalated çalıştırmalarda komutlar yürütüldü. Uygulama servisi, Docker servisi, OpenAI, LiveKit, Netgsm veya telefon çağrısı başlatılmadı.

# 29. Değiştirilen dosyalar

```text
CODEX_AUDIT_PHASE_5_FRONTEND.md
```
