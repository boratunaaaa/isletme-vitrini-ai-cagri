# CODEX_AUDIT_PHASE_6.md

## 1. Denetim kapsamı

Bu denetim Aşama 6 production altyapı değişiklikleriyle sınırlıdır: `compose.production.yml`, production Dockerfile'ları, Caddy yapılandırması, backup/restore scriptleri, production dokümantasyonu, `.env.production.example`, `.gitignore`, Makefile production hedefleri ve voice-agent entrypoint/pickle düzeltmesi incelendi. Kod düzeltmesi, commit veya push yapılmadı.

## 2. Başlangıç git durumu

- Çalışma klasörü: `/Users/kadirugur/Projects/isletme-vitrini-ai-cagri`
- Branch: `main`
- HEAD: `0cd7b73f98d4c8b9e24227cdd25ae613b03bda0a`
- Beklenen HEAD `0cd7b73` ile uyumlu.
- Son commitler: `0cd7b73 feat: add secure AI call center management panel`, `03bfa9e feat: establish tested AI call center baseline`
- Commit/push yapılmadı.
- Başlangıçta production infra dosyaları untracked/değişmiş durumdaydı; testler sırasında `.pnpm-store/` altında iki generated WAL/SHM dosyası da untracked hale geldi.

## 3. İncelenen dosyalar

İncelenen ana dosyalar: `PRODUCTION_INFRA_REPORT.md`, `compose.production.yml`, `.env.production.example`, `.gitignore`, `.dockerignore`, `Makefile`, `services/api/Dockerfile`, `apps/web/Dockerfile`, `infrastructure/docker/voice-agent.Dockerfile`, `infrastructure/docker/backup.Dockerfile`, `deploy/caddy/Caddyfile`, `deploy/caddy/Caddyfile.local`, `deploy/caddy/compose.local-caddy.override.yml`, `deploy/systemd/*`, `scripts/backup/*.sh`, `docs/production/*.md`, `services/voice-agent/agent/job_handler.py`, `services/voice-agent/agent/main.py`, `services/voice-agent/tests/test_runtime_adapters.py`, `services/voice-agent/tests/test_main.py`, `apps/web/lib/api/client.ts`, `apps/web/lib/hooks/use-live-events.ts`.

## 4. Claude raporu iddialarının doğrulama tablosu

| İddia | Durum | Kanıt |
|---|---|---|
| HEAD beklenen baseline üstünde | Doğrulandı | `git rev-parse HEAD` çıktısı `0cd7b73f...` |
| Production compose config geçiyor | Doğrulandı | Güvenli dummy env ile `docker compose --env-file /tmp/ivac-phase6-compose.env -f compose.production.yml config -q` ve `--profile tools config -q` exit 0 |
| Normal profilde 8 servis | Doğrulandı | `config --services`: postgres, redis, beat, api, frontend, caddy, voice-agent, worker |
| Tools profiliyle 10 servis | Doğrulandı | `--profile tools config --services`: migration ve backup dahil |
| 7 build target image build oluyor | Doğrulandı | `docker compose ... --profile tools build` exit 0; api/worker/beat/migrate, frontend, voice-agent, backup build edildi |
| Caddy config geçerli | Doğrulandı | `docker run ... caddy:2-alpine caddy validate` -> `Valid configuration` |
| Backend kalite kapıları | Doğrulandı | Ruff geçti; MyPy geçti; `129 passed, 3 warnings` |
| Voice-agent kalite kapıları | Doğrulandı | Ruff geçti; MyPy geçti; `111 passed` |
| Frontend kalite kapıları | Doğrulandı | `pnpm lint`, `pnpm typecheck`, `pnpm test` 33 passed, `pnpm build` geçti |
| Playwright discovery | Doğrulandı | `pnpm exec playwright test --list` -> 23 test |
| Root workspace test | Ortam ön koşulu nedeniyle geçmedi | `pnpm test` E2E backend yok diye durdu; Vitest kısmı geçti |
| Root workspace build | Doğrulandı | İlk paralel deneme E2E çakışmasıyla bozuldu; tek başına tekrar çalıştırıldığında geçti |
| Backup script | Kısmen doğrulandı | Disposable Postgres üzerinde default backup script exit 0 üretti |
| Restore smoke test | Doğrulandı | Doğru `--entrypoint /scripts/restore-smoke-test.sh` ile tüm adımlar geçti |
| Remote enabled + credential eksik | Doğrulandı | Exit 1 verdi; fakat `.last-success` yine güncellendi, bkz. YÜKSEK-1 |
| Full stack 8/8 healthy | Yeniden üretilmedi | Gerçek LiveKit/OpenAI credential olmadan tam stack başlatılmadı |
| Public proxy kontrolleri | Yeniden üretilmedi | Tam stack/Caddy proxy akışı başlatılmadı; statik Caddy validate ve compose denetimi yapıldı |

## 5. Kritik bulgular

### KRİTİK-1: Production frontend API base URL `/api/api/*` çağrılarına dönüşüyor

- Dosya/satır: `.env.production.example:20-21`, `compose.production.yml:331-337`, `apps/web/lib/api/client.ts:46-67`, `apps/web/lib/hooks/use-live-events.ts:76-80`, `docs/production/DEPLOYMENT.md:66-70`
- Sorun: Örnek production env `API_URL=https://panel.example.com/api` veriyor. Compose bunu `NEXT_PUBLIC_API_URL` build arg'ı olarak frontend bundle'a gömüyor. Frontend client ise tüm endpoint path'lerini zaten `/api/...` ile çağırıyor (`new URL(`${API_BASE_URL}${path}`)`). Sonuç: login dahil çağrılar `https://panel.example.com/api/api/auth/me`, SSE `https://panel.example.com/api/api/live/events` olur.
- Gerçek etkisi: Production paneli Caddy ve backend sağlıklı görünse bile auth, dashboard, SSE ve bütün backend bağlantıları 404/contract dışı path'e düşer. Bu, production yönetim panelini kullanılmaz hale getirebilir.
- Nasıl doğrulandı: `rg` ile tüm API kullanımları çıkarıldı; client satır 46 ve 67'de base + `/api/...` birleştirmesi, env örneği satır 21'de `/api` suffix'i, compose satır 337'de doğrudan build arg aktarımı görüldü. Caddy yalnız `/api/*` path'i backend'e taşır; `/api/api/*` backend contract'ında yok.
- Önerilen en küçük düzeltme: Frontend build arg için public origin kullanın (`NEXT_PUBLIC_API_URL=https://panel.example.com`) veya ayrı `NEXT_PUBLIC_API_BASE_URL` değişkeni tanımlayın. Backend `API_URL` ayrı amaçla `/api` bekliyorsa aynı değişkeni frontend build arg olarak paylaşmayın. Production docs ve `.env.production.example` bu ayrımı netleştirmeli.

## 6. Yüksek bulgular

### YÜKSEK-1: Off-site backup başarısız olsa bile `.last-success` güncelleniyor

- Dosya/satır: `scripts/backup/postgres-backup.sh:93-104`, `docs/production/BACKUP_AND_RESTORE.md:167-178`, `Makefile:126-128`
- Sorun: `.last-success`, off-site upload çağrısından önce yazılıyor. `BACKUP_REMOTE_ENABLED=true` iken restic credential eksik/yanlışsa script exit 1 veriyor, fakat `make backup-status` ve dokümanda önerilen `.last-success` yaşı kontrolü en son başarısız remote denemesini "son başarılı backup" gibi gösterebiliyor.
- Gerçek etkisi: Monitoring yalnız `.last-success` yaşına bakarsa off-site felaket kurtarma hedefi güncel olmadığı halde backup başarılı sanılabilir.
- Nasıl doğrulandı: Disposable Compose project üzerinde `BACKUP_REMOTE_ENABLED=true`, boş `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` ile backup çalıştırıldı. Komut exit 1 verdi; hemen sonra `/backups/.last-success` içeriği aynı başarısız denemenin timestamp'ini gösterdi.
- Önerilen en küçük düzeltme: `.last-success` yazımını off-site adımından sonra taşıyın veya marker'ı ikiye ayırın: `.last-local-success` ve `.last-remote-success`. `backup-status` ve dokümantasyon remote-enabled durumda remote marker'ı esas almalı.

### YÜKSEK-2: Restore script hedef DB adını SQL'e escape etmeden gömüyor

- Dosya/satır: `scripts/backup/postgres-restore.sh:130-145`
- Sorun: `target_db`, SQL string ve identifier bağlamlarına doğrudan interpolate ediliyor: `datname = '${target_db}'`, `DROP DATABASE "${target_db}"`, `CREATE DATABASE "${target_db}"`.
- Gerçek etkisi: Restore yüksek riskli bir operasyondur. Hedef DB adında quote veya SQL ayırıcı karakterleri varsa komut beklenmeyen SQL çalıştırabilir ya da yanlış DB üzerinde destructive işlem riski oluşturabilir. Operatör kontrollü input olduğu için dış saldırı yüzeyi değil, fakat production restore güvenliği için kabul edilemez derecede gevşek.
- Nasıl doğrulandı: Script satırları doğrudan okundu; `psql` değişkeni, identifier escaping veya allowlist regex'i yok.
- Önerilen en küçük düzeltme: `target_db` için katı regex allowlist (`^[a-zA-Z_][a-zA-Z0-9_]{0,62}$`) ekleyin ve SQL üretimini `psql` değişkenleri veya güvenli `createdb/dropdb -- "$target_db"` komutlarıyla yapın.

### YÜKSEK-3: Production placeholder secret'ları genel olarak fail-fast reddedilmiyor

- Dosya/satır: `.env.production.example:31-72`, `services/api/app/config.py:132-147`, `services/voice-agent/agent/config.py:90-117`, `docs/production/SECURITY_CHECKLIST.md:18-24`
- Sorun: Dokümantasyon `REPLACE_ME` değerlerini değiştirmeyi söylüyor, fakat uygulama tarafı yalnız eksik değerleri ve backend'de internal token uzunluğunu/dev-prefix'ini reddediyor. `JWT_SECRET=REPLACE_ME`, `COOKIE_SECRET=REPLACE_ME`, `PII_ENCRYPTION_KEY=REPLACE_ME`, `PHONE_HASH_PEPPER=REPLACE_ME`, LiveKit/OpenAI placeholder'ları genel olarak "placeholder" diye reddedilmiyor.
- Gerçek etkisi: Operatör bazı değerleri değiştirip bazı placeholder'ları unutursa servisler zayıf veya sahte credential ile başlayabilir. Voice-agent için sahte ama dolu credential'lar config validation'ı geçebilir ve runtime'da bağlantı hatasına dönüşür.
- Nasıl doğrulandı: `.env.production.example` placeholder'ları ve iki config validator satırları karşılaştırıldı. Security checklist bu riski "dolu ama zayıf değer elle doğrulanmalı" diye açıkça kabul ediyor.
- Önerilen en küçük düzeltme: Production config validation'da `REPLACE_ME`, `example`, `dummy`, `changeme` gibi placeholder değerleri ve minimum uzunluk/entropi eşiğini tüm kritik secret'lar için reddedin. `.env.production.example` zorunlu secret'ları boş bırakıp compose `${VAR:?}` fail-fast davranışını da kullanabilirsiniz.

## 7. Orta bulgular

### ORTA-1: `.pnpm-store/` Git ignore kapsamında değil

- Dosya/satır: `.gitignore:11-24`, `.dockerignore:11-22`
- Sorun: `.dockerignore` `.pnpm-store/` kapsıyor, fakat `.gitignore` kapsamıyor. Frontend doğrulama komutları sonrası `.pnpm-store/v11/index.db-shm` ve `.pnpm-store/v11/index.db-wal` untracked olarak göründü.
- Gerçek etkisi: `git add .` ile pnpm cache/WAL artefact'ları commit adayına girebilir.
- Nasıl doğrulandı: `git status --short` ve `git ls-files --others --exclude-standard` çıktıları `.pnpm-store/` gösterdi; `git check-ignore -v .pnpm-store/v11/index.db-wal` eşleşme döndürmedi.
- Önerilen en küçük düzeltme: `.gitignore` içine `.pnpm-store/` ekleyin ve bu generated artefact'ları stage etmeyin.

### ORTA-2: Caddy access log query string/token/PII redaksiyonu yok

- Dosya/satır: `deploy/caddy/Caddyfile:101-104`
- Sorun: Caddy JSON access log stdout'a yazılıyor; log filter/redaction yapılandırması yok.
- Gerçek etkisi: Kullanıcı veya test akışları query string içinde `next`, import parametreleri, token benzeri değerler ya da PII taşıyacak şekilde genişlerse reverse proxy logları bunu saklayabilir. Mevcut auth token'ı cookie/header ile taşındığından bugünkü doğrudan secret sızıntısı görülmedi, ancak reverse proxy katmanı PII-safe değil.
- Nasıl doğrulandı: Caddyfile log bloğu yalnız `output stdout` ve `format json` içeriyor; filter/uri masking yok.
- Önerilen en küçük düzeltme: Caddy log formatında query'yi düşürün veya hassas alanları filtreleyin; ayrıca docs'ta access log saklama/redaction politikasını belirtin.

### ORTA-3: Backup image root olarak çalışıyor ve compose hardening almıyor

- Dosya/satır: `infrastructure/docker/backup.Dockerfile:6-19`, `compose.production.yml:382-412`
- Sorun: Backup image'da non-root `USER` yok; backup service için `cap_drop`, `no-new-privileges`, `read_only` veya tmpfs hardening uygulanmamış.
- Gerçek etkisi: Tool profile altında ve sürekli çalışan servis değil, ancak DB credential ve backup volume erişimi olan container root çalışıyor. Hata/kompromize durumda etki alanı gereğinden geniş.
- Nasıl doğrulandı: Dockerfile ve compose servis tanımı okundu.
- Önerilen en küçük düzeltme: Backup volume izinleriyle uyumlu non-root kullanıcı ekleyin; mümkünse `cap_drop: [ALL]`, `security_opt: no-new-privileges`, sadece gerekli writable mount'lar ve tmpfs kullanın.

### ORTA-4: Restore smoke test gerçek restore script'ini çağırıyor, fakat gerçek backup script'ini tam uçtan uca çağırmıyor

- Dosya/satır: `scripts/backup/restore-smoke-test.sh:65-71`
- Sorun: Smoke test backup üretiminde `postgres-backup.sh` yerine aynı `pg_dump | gzip` komutunu kendi içinde çalıştırıyor. Bu nedenle lock, retention, `.last-success`, off-site çağrı sıralaması ve backup script cleanup davranışı bu test tarafından kapsanmıyor.
- Gerçek etkisi: Restore yolu kanıtlı, fakat backup script'in operasyonel yan etkileri için test güvencesi daha zayıf.
- Nasıl doğrulandı: Smoke script satır 67-68 doğrudan `pg_dump --format=plain | gzip` kullanıyor. Ayrıca audit sırasında default backup script ayrı çalıştırıldı ve local success verdi.
- Önerilen en küçük düzeltme: Smoke test'te gerçek `postgres-backup.sh` için izole `BACKUP_DIR` kullanın veya ayrı bir backup-script integration test ekleyin.

### ORTA-5: Production health dokümanı compose ile uyuşmuyor

- Dosya/satır: `docs/production/DEPLOYMENT.md:108-110`, `compose.production.yml:239-244`, `compose.production.yml:280-285`
- Sorun: Doküman worker/beat için Docker healthcheck tanımlı değildir diyor; compose'da worker ve beat healthcheck'leri mevcut.
- Gerçek etkisi: Operatör `docker compose ps` health sonuçlarını yanlış yorumlayabilir.
- Nasıl doğrulandı: Doküman ve compose satırları karşılaştırıldı.
- Önerilen en küçük düzeltme: Dokümanı güncel compose davranışıyla hizalayın.

### ORTA-6: Backup formatı plain SQL; custom format/pg_restore doğrulaması yok

- Dosya/satır: `scripts/backup/postgres-backup.sh:52`, `scripts/backup/postgres-restore.sh:147-151`, `docs/production/BACKUP_AND_RESTORE.md:68-71`
- Sorun: Backup `pg_dump --format=plain | gzip` kullanıyor; restore `psql` ile yapılıyor. `pg_restore --list` veya custom format'ın nesne seviyesinde doğrulama/restore avantajları yok.
- Gerçek etkisi: Mevcut smoke test küçük veri için geçiyor, ancak büyük production restore'da seçici restore, list validation ve bazı hata izolasyonu daha zayıf kalır.
- Nasıl doğrulandı: Script satırları ve restore smoke test çalıştırıldı.
- Önerilen en küçük düzeltme: Ya plain format tercihinin gerekçesini açık trade-off olarak yazın ya da custom format + `pg_restore --list`/`pg_restore` tabanlı restore'a geçin.

## 8. Düşük bulgular

### DÜŞÜK-1: Caddy validate format uyarısı ve gereksiz header uyarıları veriyor

- Dosya/satır: `deploy/caddy/Caddyfile:78-91`
- Sorun: `caddy validate` geçiyor, ancak `header_up X-Forwarded-Proto` ve `X-Forwarded-For` için gereksiz uyarı, ayrıca `caddy fmt` önerisi veriyor.
- Gerçek etkisi: İşlevsel kırılma yok; bakım ve log gürültüsü.
- Nasıl doğrulandı: Resmi `caddy:2-alpine` image ile `caddy validate` çalıştırıldı.
- Önerilen en küçük düzeltme: Caddyfile'ı `caddy fmt` ile hizalayın; gereksiz `header_up` satırlarını bilinçli gerekçe yoksa kaldırın.

### DÜŞÜK-2: API Docker CMD tüm forwarded proxy IP'lerine güveniyor

- Dosya/satır: `services/api/Dockerfile:53`, `compose.production.yml:192`, `docs/production/SECURITY_CHECKLIST.md:60-65`
- Sorun: Uvicorn `--forwarded-allow-ips=*` ile çalışıyor. Compose'da API host port açmadığı ve Caddy header'ları set ettiği için pratik risk düşük.
- Gerçek etkisi: Edge network içinde beklenmeyen başka bir container API'ye istek atabilirse client IP/proto spoof edebilir.
- Nasıl doğrulandı: Dockerfile ve network tanımı okundu.
- Önerilen en küçük düzeltme: Mümkünse Caddy container IP aralığını/servis adını daraltın veya API edge network üyeliğini daha sıkı belgeleyin.

### DÜŞÜK-3: Full stack health/proxy akışı gerçek credential olmadan yeniden üretilmedi

- Dosya/satır: `PRODUCTION_INFRA_REPORT.md:140-186`
- Sorun: Audit kapsamında full `up -d`, `/health`, `/ready`, proxy ve unauthorized API kontrolleri bugün yeniden koşturulmadı.
- Gerçek etkisi: Dockerfile/build/config ve bazı backup/restore yolları doğrulandı; ancak runtime health iddiası ikinci kez canlı kanıtlanmadı.
- Nasıl doğrulandı: Test kapsamı bilinçli sınırlı tutuldu; gerçek LiveKit/OpenAI credential bulunmadığı için voice-agent full runtime başlatılmadı.
- Önerilen en küçük düzeltme: Kritik bulgular kapandıktan sonra staging/dummy domain ortamında full stack smoke test'i tekrarlayın.

## 9. Dockerfile değerlendirmesi

API, frontend ve voice-agent image'ları multi-stage yapı kullanıyor, lock dosyalarıyla deterministik kurulum hedefliyor, final stage'de non-root kullanıcıya geçiyor ve exec-form CMD kullanıyor. `.dockerignore` repo kökü build context için doğru şekilde `.env*`, `.git`, cache, test artefact'ları, `.pnpm-store/`, `.next/`, `.venv/` ve dokümanları dışlıyor.

Backup image PostgreSQL 16 tabanıyla server sürüm uyumunu koruyor ve restic içeriyor; ancak root çalışması ve compose hardening eksikliği ORTA-3 olarak işaretlendi.

Production image build güvenli dummy env ile yeniden üretildi; 7 build target exit 0 verdi. Caddy resmi image kullanıldığı için build target değil, runtime image olarak validate edildi.

## 10. Compose/network/public port değerlendirmesi

`compose.production.yml config -q` ve `--profile tools config -q` geçti. Normal profilde 8 servis, tools profiliyle 10 servis doğrulandı. Compose satır 355-358 yalnız Caddy için 80/tcp, 443/tcp ve 443/udp yayınlıyor; backend/frontend/db/redis host port açmıyor. `data` ağı `internal: true`; postgres/redis yalnız `data` ağında. Caddy yalnız `edge` ağında ve DB/Redis'e bağlı değil. Frontend yalnız `edge` ağında.

Semantik olarak en büyük sorun frontend build arg'ının yanlış `API_URL` suffix'iyle beslenmesi; compose schema bunu yakalayamıyor.

## 11. Caddy/TLS/proxy değerlendirmesi

Caddyfile resmi `caddy:2-alpine` ile validate edildi ve geçerli bulundu. Route sırası `handle @internal`, `handle @health`, `handle @api`, catch-all frontend şeklinde doğru. `/api/internal/*` public erişimde 403 döndürecek şekilde önce yakalanıyor. `/health` ve `/ready` backend'e gidiyor. SSE yolu `/api/live/events` için compression dışlama matcher'ı var ve API reverse proxy içinde `flush_interval -1` kullanılmış.

Kalan riskler: access log redaction yok (ORTA-2), format/header uyarıları var (DÜŞÜK-1). Full proxy runtime istekleri bu audit'te yeniden koşturulmadı.

## 12. PostgreSQL backup değerlendirmesi

`postgres-backup.sh` güvenli shell modları, UTC timestamp, temp dosya + atomik `mv`, gzip bütünlük kontrolü, içerik imzası, SHA-256 checksum, `flock`, disk alanı ön kontrolü ve retention içeriyor. Parola argv'ye konmuyor; `PGPASSWORD` env ile libpq'ya bırakılıyor.

Disposable PostgreSQL üzerinde local backup başarıyla çalıştı. Ancak off-site etkin ama credential eksik durumda script exit 1 verse de `.last-success` güncellendi (YÜKSEK-1). Backup formatı plain SQL olduğu için custom format/pg_restore avantajları yok (ORTA-6).

## 13. Restore güvenliği değerlendirmesi

Restore script checksum olmadan başlamıyor, gzip kontrolü yapıyor, `--force` zorunlu, production DB adıyla aynı hedefte `--allow-production-overwrite` istiyor. Disposable restore smoke test gerçek `postgres-restore.sh` yolunu çalıştırdı ve corrupt checksum restore başlamadan reddedildi.

Kalan yüksek risk: hedef DB adı SQL'e güvenli escape/allowlist olmadan gömülüyor (YÜKSEK-2). Ayrıca production restore prosedürü plain SQL restore sırasında transaction/disposable swap yaklaşımı sunmuyor; bu ORTA-6 kapsamındaki format/restore mimarisiyle ilişkili.

## 14. Restic/off-site değerlendirmesi

`offsite-backup.sh` restic repository/password gerektiriyor, backup sonrası `restic check`, ardından `forget --prune` çalıştırıyor. Secret değerleri argüman olarak geçmiyor, env ile taşınıyor. Credential eksik yolu non-zero olarak doğrulandı.

Off-site başarı yolu gerçek credential olmadığı için test edilmedi. Bu durum production açılışı için operasyonel blokerdir. Ayrıca YÜKSEK-1 nedeniyle remote-enabled başarısızlık `.last-success` ile karışabiliyor.

## 15. Scheduler ve operasyon değerlendirmesi

Backup zamanlaması host systemd timer ile yapılmış; `Persistent=true`, UTC takvim ve randomized delay mevcut. Sonsuz `while sleep` scheduler yok. Manuel `make backup` ile timer aynı anda çalışırsa script içindeki `flock` backup volume üzerinde ikinci çalışmayı reddeder.

Eksikler: harici alert mekanizması yok, yalnız runbook/monitoring önerisi var. `.last-success` marker'ı remote başarısızlıkta güvenilir olmadığı için scheduler/monitoring değerlendirmesi YÜKSEK-1'den etkileniyor.

## 16. Voice-agent pickle düzeltmesi değerlendirmesi

Önceki closure problemi için `entrypoint(ctx)` modül seviyesine taşınmış (`services/voice-agent/agent/job_handler.py:483-507`) ve `build_server()` bunu `server.rtc_session(entrypoint, agent_name=...)` ile kaydediyor (`510-517`). `run_worker()` runtime config validation sonrası `agents.cli.run_app(server)` çağırıyor.

Regresyon testi `pickle.dumps(entrypoint)` ve `pickle.loads(...)` ile modül seviyesi picklability'yi doğruluyor (`services/voice-agent/tests/test_runtime_adapters.py:249-263`). Bu test gerçek LiveKit process pool'u çalıştırmıyor, ancak yakalanan hata sınıfı için anlamlı minimum regresyon testi. Değişiklik call lifecycle, termination logic veya credential taşıma davranışını genişletmiyor.

## 17. Test sonuçları

Çalıştırılan doğrulamalar:

- `git diff --check`: geçti
- `git diff --summary`: çıktı yok
- `git ls-files '*.env*'`: yalnız `.env.example`, `apps/web/.env.example`
- `git check-ignore -v .env.production`: `.gitignore:3:.env.*`
- Production compose config normal/tools: geçti
- Caddy validate: geçti
- Production image build: geçti
- Backend Ruff: geçti
- Backend MyPy: geçti
- Backend Pytest: `129 passed, 3 warnings`
- Voice-agent Ruff: geçti
- Voice-agent MyPy: geçti
- Voice-agent Pytest: `111 passed`
- Frontend lint: geçti
- Frontend typecheck: geçti
- Frontend Vitest: `33 passed`
- Frontend build: geçti
- Playwright discovery: `23 tests`
- Root lint/typecheck/build: geçti
- Root test: E2E backend ön koşulu olmadığı için fail; web Vitest kısmı geçti
- Disposable Postgres local backup: geçti
- Disposable restore smoke test: geçti
- Remote enabled + eksik restic credential: exit 1, fakat `.last-success` güncellendi

Çalıştırılmayanlar: full production stack `up -d`, public port runtime probe, Caddy proxy canlı `/health`/`/ready`/`/api/internal/*` istekleri, gerçek off-site başarı yolu, gerçek OpenAI/LiveKit/Netgsm/telefon akışları.

## 18. Secret/PII ve git hijyeni

`.env.production` çalışma ağacında ignored durumda ve tracked değil. `git ls-files '*.env*'` yalnız örnek env dosyalarını gösterdi. Secret taramasında gerçek key/token bulunmadı; eşleşmeler doküman, placeholder ve açıkça sahte test değerlerinden ibaret. PII taramasında gerçek lead listesi, transcript, ses kaydı veya müşteri verisi bulunmadı.

`find` çıktısında `.venv` içi certificate PEM'leri ve `infrastructure/scripts/init-test-db.sql` göründü; `.venv` ignored, SQL test init dosyası repo geçmişinde mevcut. Büyük dosyalar `node_modules`, `.next`, `.venv`, cache klasörlerinde ve ignored kapsamda. Ancak `.pnpm-store/` şu an `.gitignore` kapsamında değil ve untracked olarak görünüyor (ORTA-1).

Script permission'ları: `scripts/backup/*.sh` executable; systemd unit/timer dosyaları normal read-only mode ile uygun.

## 19. Dokümantasyon doğruluğu

Production dokümanları migration, backup, restore drill, off-site backup eksikliği ve volume silme riskini genel olarak doğru anlatıyor. `docker compose down -v` rutin komut olarak önerilmemiş; `prod-destroy-volumes force=yes` ayrı ve açık tehlikeli hedef.

Yanlış/eksik noktalar:

- `DEPLOYMENT.md` frontend build arg'ın `API_URL`'den geldiğini yazıyor ama `.env.production.example` bu değişkeni `/api` suffix'iyle veriyor; bu KRİTİK-1'i dokümana da taşıyor.
- `DEPLOYMENT.md` health bölümünde worker/beat için healthcheck yok deniyor, compose'da var (ORTA-5).
- Backup status dokümantasyonu `.last-success` yaşına bakmayı öneriyor, ancak remote-enabled başarısızlıkta bu marker güncelleniyor (YÜKSEK-1).
- Security checklist placeholder riskini elle kontrol maddesi yapmış; fail-fast otomatik değil (YÜKSEK-3).

## 20. Commit kapsamına alınması önerilen dosyalar

Kritik/yüksek bulgular düzeltildikten sonra commit kapsamına alınabilecek dosyalar: production compose, Dockerfile'lar, Caddy dosyaları, backup/restore scriptleri, systemd unit/timer, production dokümantasyonları, `.env.production.example`, `.dockerignore`, `.gitignore`, Makefile production hedefleri, voice-agent entrypoint ve test dosyaları, `PRODUCTION_INFRA_REPORT.md`.

Bu rapor dosyası (`CODEX_AUDIT_PHASE_6.md`) denetim çıktısı olarak commit kapsamına alınabilir.

## 21. Commit dışında bırakılması gereken dosyalar

- `.env.production`
- `.pnpm-store/`
- `node_modules/`, `.next/`, `.turbo/`
- `.venv/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `.coverage`
- `tests/e2e/.auth/`, `test-results/`, `playwright-report/`
- Backup dump/checksum artefact'ları, loglar, ses/transcript dosyaları, private key/cert dosyaları

Bugünkü denetim sonunda `.pnpm-store/` untracked göründüğü için commit öncesi mutlaka ignore edilmeli veya stage dışı bırakılmalıdır. Dosya silinmedi.

## 22. Nihai karar

**RED — KRİTİK/YÜKSEK sorunlar nedeniyle commit edilmemeli**

Gerekçe: KRİTİK-1 production frontend'in backend'e yanlış `/api/api/*` path'leriyle bağlanmasına yol açıyor ve yönetim panelini production'da kullanılamaz hale getirebilir. Ayrıca backup/restore güvenliği açısından YÜKSEK-1, YÜKSEK-2 ve YÜKSEK-3 commit öncesi düzeltilmelidir.

Kod commit için hazır değil. Production açılışı için ayrıca gerçek off-site backup credential'larıyla başarı yolu, restore drill ve full stack proxy/health smoke testleri tamamlanmadan "production ready" denmemelidir.
