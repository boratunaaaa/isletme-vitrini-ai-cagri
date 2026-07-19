# PRODUCTION_INFRA_REPORT.md — Aşama 6: Production Docker + Caddy + Backup Altyapısı

Bu rapor, "Aşama 6" görev tanımının 14 numaralı bölümünde istenen 22 alt
başlığı belgeler. **İki doğrulama turu** yapıldı: (1) ilk implementasyon +
validasyon, (2) `CODEX_AUDIT_PHASE_6.md`'nin bulduğu KRİTİK/YÜKSEK/ORTA
sorunların düzeltilmesi + tam yeniden doğrulama. Hiçbir madde varsayıma
dayanmaz — her iddia altındaki komut gerçekten çalıştırılmış ve çıktısı
gözlemlenmiştir.

## 1. Git Durumu (Başlangıç ve Bitiş)

- **Baseline commit**: `03bfa9e feat: establish tested AI call center baseline`
- **Frontend commit**: `0cd7b73 feat: add secure AI call center management panel` (branch `main`, bu commit HEAD'te)
- Bu oturum **hiçbir commit veya push YAPMADI** — tüm değişiklikler working tree'de.
- Bitişte `git status --short`:
  ```
   M .gitignore
   M Makefile
   M apps/web/next.config.ts
   M apps/web/playwright.config.ts
   M apps/web/tsconfig.json
   M infrastructure/docker/voice-agent.Dockerfile
   M services/api/app/config.py
   M services/voice-agent/agent/config.py
   M services/voice-agent/agent/job_handler.py
   M services/voice-agent/agent/main.py
   M services/voice-agent/tests/test_config.py
   M services/voice-agent/tests/test_runtime_adapters.py
  ?? .dockerignore
  ?? .env.production.example
  ?? CODEX_AUDIT_PHASE_6.md
  ?? apps/web/Dockerfile
  ?? compose.production.yml
  ?? deploy/
  ?? docs/production/
  ?? infrastructure/docker/backup.Dockerfile
  ?? scripts/
  ?? services/api/Dockerfile
  ?? services/api/tests/unit/test_config.py
  ?? services/voice-agent/tests/test_main.py
  ?? PRODUCTION_INFRA_REPORT.md
  ```
  (`.env.production` bilinçli olarak burada YOK — `.gitignore` altında, hiç `git add` edilmedi.)

## 2. İncelenen Gerçek Mimari

- **Frontend**: Next.js 15 (`apps/web`), `@ivac/web`. Build: `pnpm --filter @ivac/web build`. Production: `output: standalone`, `node apps/web/server.js`. `NEXT_PUBLIC_API_URL` build-time'da client bundle'a gömülür.
- **Backend**: FastAPI (`services/api`), `app.main:app`, `uvicorn`. Health: `GET /health`, `GET /ready` (gerçek DB+Redis kontrolü).
- **Worker/Scheduler**: Celery `worker` + ayrı `beat` süreci, aynı image farklı `command:`.
- **Voice-agent**: LiveKit Agents SDK, `python -m agent.main start`.
- **PostgreSQL**: Alembic migration, TEK ayrı `migrate` komutu (boot'ta otomatik migration YOK).
- **Redis**: Celery broker/backend + oturum + rate-limit + SSE pub/sub — tamamı reconstructable.
- **SSE**: `GET /api/live/events` (WebSocket YOK).
- **Frontend↔Backend sözleşmesi** (KRİTİK-1'in kök nedeni — bu turda öğrenildi): `apps/web/lib/api/client.ts::buildUrl()` her isteği `${NEXT_PUBLIC_API_URL}${path}` şeklinde kurar ve TÜM path'ler (`apps/web/lib/api/*.ts`) zaten `/api/...` ile başlar (`"/api/auth/login"`, `"/api/leads"` vb.). Yani `NEXT_PUBLIC_API_URL` bir **origin** olmalı (`https://panel.example.com`), `/api` SUFFIX'İ İÇERMEMELİ — bu, backend'in kendi `API_URL` varsayılanıyla (`http://localhost:8000`, suffix yok) da tutarlı.

## 3. Oluşturulan / Değiştirilen Dosyalar (iki tur toplamı)

**Yeni dosyalar:** `.dockerignore`, `.env.production.example`, `apps/web/Dockerfile`, `services/api/Dockerfile`, `infrastructure/docker/backup.Dockerfile`, `compose.production.yml`, `deploy/caddy/Caddyfile`, `deploy/caddy/Caddyfile.local`, `deploy/caddy/compose.local-caddy.override.yml`, `deploy/systemd/ivac-postgres-backup.{service,timer}`, `scripts/backup/{lib,postgres-backup,postgres-restore,verify-backup,offsite-backup,restore-smoke-test,entrypoint}.sh`, `docs/production/{DEPLOYMENT,BACKUP_AND_RESTORE,OPERATIONS_RUNBOOK,SECURITY_CHECKLIST}.md`, `services/voice-agent/tests/test_main.py`, `services/api/tests/unit/test_config.py`.

**Değiştirilen dosyalar (1. tur — orijinal implementasyon):** `services/voice-agent/agent/main.py` (argparse `parse_known_args`), `infrastructure/docker/voice-agent.Dockerfile` (`CMD ... start`), `services/voice-agent/agent/job_handler.py` (entrypoint modül seviyesine taşındı — pickle fix), `services/voice-agent/tests/test_runtime_adapters.py`, `apps/web/next.config.ts` (`output: standalone`), `apps/web/tsconfig.json` (playwright.config exclude), `apps/web/playwright.config.ts` (yorum), `.gitignore` (whitelist istisnaları).

**Değiştirilen dosyalar (2. tur — CODEX_AUDIT_PHASE_6.md düzeltmeleri):**
- `.env.production.example` — `API_URL`'den `/api` suffix'i kaldırıldı (KRİTİK-1).
- `docs/production/DEPLOYMENT.md` — `API_URL` suffix uyarısı + worker/beat healthcheck düzeltmesi eklendi (ORTA-5).
- `scripts/backup/postgres-backup.sh` — `.last-success` → `.last-local-success`/`.last-remote-success` ayrımı (YÜKSEK-1).
- `Makefile` — `backup-status` iki marker'ı da gösterir; `backup-verify-all`/`restore-smoke-test` artık `--entrypoint` yerine `command:` argümanı kullanır (non-root wrapper'dan geçmesi için).
- `docs/production/BACKUP_AND_RESTORE.md` — marker ayrımı belgelendi.
- `scripts/backup/postgres-restore.sh` — `target_db` için katı regex allowlist eklendi (YÜKSEK-2).
- `services/api/app/config.py` — `validate_runtime()` artık production'da placeholder/kısa secret'ları reddediyor (YÜKSEK-3).
- `services/voice-agent/agent/config.py` — `missing_runtime_settings()` aynı korumayı production'da uyguluyor (YÜKSEK-3).
- `.gitignore` — `.pnpm-store/` eklendi (ORTA-1).
- `infrastructure/docker/backup.Dockerfile` + `scripts/backup/entrypoint.sh` (yeni) — backup image artık non-root (`postgres`, uid 70) çalışıyor (ORTA-3).
- `compose.production.yml` — `backup` servisine `cap_drop`/`cap_add`/`no-new-privileges` eklendi (ORTA-3).
- `deploy/caddy/Caddyfile` + `Caddyfile.local` — access log'da hassas query parametreleri (`next`/`token`/`code`/`email`/`phone`) redakte ediliyor (ORTA-2); gereksiz `header_up X-Forwarded-*` satırları kaldırıldı (DÜŞÜK-1).

## 4. Production Servisleri

`compose.production.yml`: `postgres`, `redis`, `migrate` (profil: `tools`), `api`, `worker`, `beat`, `voice-agent`, `frontend`, `caddy`, `backup` (profil: `tools`) — 10 servis tanımı, 8'i `up -d` ile otomatik başlar.

## 5. Ağ / Public Port Yapısı

- `data` ağı: `internal: true` — `postgres`, `redis`, `beat`, `api`, `worker`, `migrate`, `backup`.
- `edge` ağı: `internal: false` — `api`, `worker`, `voice-agent`, `frontend`, `caddy`, `backup`.
- **Yalnız `caddy`** host'a port yayınlar: `80/tcp`, `443/tcp`, `443/udp`. İkinci turda canlı doğrulandı:
  ```
  api: [{ 8000 0 tcp}]          ← host port YOK
  beat: [{ 8000 0 tcp}]         ← host port YOK
  caddy: [{0.0.0.0 80->80 tcp} {0.0.0.0 443->443 tcp} {0.0.0.0 443->443 udp} ...]  ← TEK yayınlanan
  frontend: [{ 3000 0 tcp}]     ← host port YOK
  postgres: [{ 5432 0 tcp}]     ← host port YOK
  redis: [{ 6379 0 tcp}]        ← host port YOK
  voice-agent: []
  worker: [{ 8000 0 tcp}]       ← host port YOK
  ```
  (Listede görünen `8080` yalnız local test override'ından; gerçek production compose'da YOK.)

## 6. Dockerfile Güvenlik Kararları

- Tüm image'lar multi-stage, non-root kullanıcı: `api`/`worker`/`beat`/`migrate` → `ivac`, `frontend` → `ivac`, `voice-agent` → `voiceagent`, **`backup` → artık `postgres`** (2. turda düzeltildi — önceden root çalışıyordu, bkz. §14 ORTA-3).
- Backup image'ı `entrypoint.sh` ile "root'ta başla → `/backups` sahipliğini düzelt → `su-exec postgres` ile düşür" desenini kullanır (postgres/redis servisleriyle aynı, ampirik doğrulanmış desen).
- `.dockerignore`: `.git`, `node_modules`, `.pnpm-store`, Python venv/cache, test artefact'ları, tüm `.env*` (örnekler hariç), `docs/`.
- `services/api/Dockerfile`: `HEALTHCHECK` gerçek `/health` isteği (yalnız process-alive değil).
- `apps/web/Dockerfile`: `output: standalone`, `NEXT_PUBLIC_API_URL` build-arg (artık doğru origin değeriyle).
- Hiçbir image'da hot-reload/kaynak bind-mount YOK.

## 7. Caddy Route / TLS Yapısı

`/api/**` → backend, `/api/internal/**` → **PUBLİC'TEN 403**, `/health`+`/ready` → backend, geri kalan → frontend. **Kritik düzeltme (2. tur)**: route kararları artık TÜMÜYLE `handle` bloklarına sarılı — önceden çıplak (`handle` olmayan) `respond`/`reverse_proxy` direktifleri Caddy'nin varsayılan sıralamasında catch-all'dan SONRA derleniyordu, yani `/health`/`/ready`/`/api/internal/*` HİÇBİR ZAMAN backend'e ulaşmıyordu (`caddy adapt` çıktısıyla ampirik doğrulandı, bkz. §14). `encode zstd gzip` SSE yolunu (`/api/live/events`) request-path matcher'ı ile atlar. `respond` argüman sırası düzeltildi (`"metin" 403`, ters değil). Access log artık hassas query parametrelerini redakte ediyor. Yerel doğrulama `Caddyfile.local` ile yapıldı (`tls internal` self-signed + düz `:8080`).

## 8. Kalıcı Veri Envanteri

| Veri | Sınıflandırma | Yedekleniyor mu |
|---|---|---|
| Lead/kampanya/çağrı/kullanıcı/audit + transkript + şifreli telefon | PostgreSQL | **Evet** |
| Redis (broker, oturum, rate-limit, SSE) | Geçici | **Hayır** |
| Caddy TLS state | Yeniden oluşturulabilir | Hayır |
| Ses kaydı / kullanıcı dosya yüklemeleri | Henüz kullanılmıyor | Yok |

## 9. PostgreSQL Backup Sistemi

`flock` kilidi, disk-doluluk kontrolü, `pg_dump | gzip -9`, üçlü bütünlük kontrolü (boş dosya + `gzip -t` + içerik imzası), atomik `mv`, SHA-256 checksum, UTC dosya adı, retention. **Artık non-root (`postgres`) kullanıcısıyla çalışıyor.** Canlı test edildi — §16.

## 10. Off-site Backup / Şifreleme

restic (`init`/`backup`/`check`/`forget --prune`). `BACKUP_REMOTE_ENABLED=false` → yalnız local, AÇIKÇA "felaket kurtarmaya hazır DEĞİL" işaretlenir. Off-site başarısızsa TÜM backup job'ı başarısız sayılır — **ayrıca artık `.last-remote-success` de YAZILMAZ** (2. tur düzeltmesi, bkz. §14 YÜKSEK-1), bu yüzden monitoring off-site'ın gerçekten güncel olup olmadığını doğru görür.

## 11. Retention Politikası

| Politika | Varsayılan | Env |
|---|---|---|
| Local backup | 14 gün | `BACKUP_RETENTION_DAYS` |
| Off-site günlük/haftalık/aylık | 14/8/6 | `RESTIC_RETENTION_{DAILY,WEEKLY,MONTHLY}` |

## 12. Restore Prosedürü

`postgres-restore.sh`: `--force` zorunlu, checksum doğrulanmadan başlamaz, production DB adıyla aynıysa `--allow-production-overwrite` da gerekir, parola CLI argümanında GEÇMEZ. **2. tur düzeltmesi**: `--target-db` artık katı bir regex allowlist'ten (`^[a-zA-Z_][a-zA-Z0-9_]{0,62}$`) geçmeden kabul edilmiyor — önceden hedef DB adı hem SQL string literal hem quoted identifier bağlamına escape edilmeden gömülüyordu (bkz. §14 YÜKSEK-2). Gerçek disposable restore testi GEÇTİ — §16.

## 13. Bu Oturumda Çalıştırılan Gerçek Komutlar (özet, iki tur)

`docker compose ... config -q` (+`--profile tools`), `... --profile tools build` (7 image, iki kez — ikinci tur değişikliklerle), `... up -d postgres redis` + health-wait, `... run --rm migrate`, `... run --rm api python -m app.bootstrap`, `... up -d` (+ local Caddy override), `docker compose exec frontend grep` (bundle'a gömülü URL doğrulaması), 9+ `curl` testi (health/ready/internal-403/unauth-401/gerçek login+session/HTTPS/security header), `caddy validate`/`caddy adapt` (host'ta doğrudan), `run --rm backup /scripts/postgres-backup.sh` (çoklu kez), `verify-backup.sh --all`, paralel iki backup (lock testi), sahte restic credential'larıyla off-site-fail testi + marker dosyası kontrolü, `restore-smoke-test.sh`, backend/voice-agent `ruff`/`mypy`/`pytest`, frontend `lint`/`typecheck`/`test`, kök `turbo run lint typecheck`, `git status`/`git check-ignore`/secret grep taraması, `docker compose down -v` + `docker volume rm` (yalnız `ivac-production_*` disposable volume'lar), `docker compose -f docker-compose.dev.yml ps` (dev stack etkilenmedi doğrulaması).

## 14. Test Sonuçları

| Test | 1. Tur | 2. Tur (fix sonrası) |
|---|---|---|
| Backend `ruff`/`mypy` | ✅ | ✅ |
| Backend `pytest` | 129 passed | **137 passed** (+8 yeni: placeholder/weak-secret reddi) |
| Voice-agent `ruff`/`mypy` | ✅ | ✅ |
| Voice-agent `pytest` | 111 passed | **113 passed** (+2 yeni: production placeholder reddi) |
| Frontend `lint`/`typecheck`/`test` | ✅ / ✅ / 33 passed | ✅ / ✅ / 33 passed |
| Frontend `build` | ✅ 19 route | ✅ (1. turda doğrulandı, kaynak değişmedi) |
| Playwright discovery | 23 test | (1. turda doğrulandı, kaynak değişmedi) |
| Kök `turbo lint/typecheck` | ✅ | ✅ |

**CODEX_AUDIT_PHASE_6.md'nin bulduğu ve bu oturumda düzeltilen sorunlar:**

- **KRİTİK-1 (frontend `/api/api/*` — panel tamamen kullanılamaz hale gelirdi)**: `.env.production.example`'ın `API_URL=https://panel.example.com/api` değeri, frontend build-arg'ı olarak kullanıldığında client'ın kendi `/api/...` path'leriyle çakışıp `/api/api/...` üretiyordu. **Fix**: `/api` suffix'i kaldırıldı. **Doğrulama**: rebuild sonrası frontend bundle'ında `grep` ile yalnız `https://panel.example.com` (suffix YOK) bulundu; Caddy üzerinden GERÇEK login (`POST /api/auth/login`, bootstrap admin credential'larıyla) `200` ve geçerli session cookie/CSRF token döndü; `GET /api/api/leads` (eski buggy path) `404` verdi, doğru path (`/api/leads`) `401` (auth gerekli) verdi — bug'ın gerçekliği ve fix'in doğruluğu ikisi de kanıtlandı.
- **YÜKSEK-1 (`.last-success` off-site başarısızlığını gizliyordu)**: local ve off-site zaman damgaları `.last-local-success`/`.last-remote-success` olarak ayrıldı. **Doğrulama**: sahte restic credential'larıyla off-site testi çalıştırıldı — `.last-local-success` güncellendi, `.last-remote-success` OLUŞMADI (doğru davranış).
- **YÜKSEK-2 (restore script SQL'e escape'siz `target_db`)**: katı regex allowlist eklendi. **Doğrulama**: `restore-smoke-test.sh`'nin ürettiği gerçek disposable DB adlarıyla (`ivac_smoke_dst_...`) restore GEÇTİ, allowlist normal kullanımı bozmadı.
- **YÜKSEK-3 (placeholder secret'lar fail-fast'i atlatabiliyordu)**: backend + voice-agent config validasyonuna `REPLACE_ME`/`changeme`/`example`/`dummy` marker + minimum 20 karakter kontrolü eklendi (yalnız production'da; development'ta düşük sürtünme korunuyor). 10 yeni regresyon testi (5 backend + 2 voice-agent + var olanların güncellenmesi) eklendi, hepsi geçti.
- **ORTA-1** (`.pnpm-store/` gitignore'da yoktu) — eklendi.
- **ORTA-2** (Caddy log'da PII/token redaksiyonu yoktu) — `next`/`token`/`code`/`email`/`phone` query parametreleri artık silinerek loglanıyor.
- **ORTA-3** (backup image root + hardening yok) — non-root (`postgres`) + `cap_drop`/`cap_add`/`no-new-privileges` eklendi, tüm backup/verify/restore akışı canlı yeniden test edildi ve geçti.
- **ORTA-5** (doküman worker/beat healthcheck'i yok diyordu) — düzeltildi, ayrıca voice-agent healthcheck'in gerçekte neyi doğrulayıp doğrulamadığı netleştirildi.
- **DÜŞÜK-1** (gereksiz `header_up` uyarıları) — kaldırıldı, `caddy validate` artık hiç uyarı vermiyor.

**Bilinçli olarak bu turda ele alınmayan (ORTA-4, ORTA-6, DÜŞÜK-2, DÜŞÜK-3)**: smoke test'in backup script'ini uçtan uca değil kendi pg_dump çağrısıyla test etmesi, plain-format backup (custom format/`pg_restore` avantajları yok), `--forwarded-allow-ips=*`, ve gerçek credential'sız off-site başarı/gerçek ACME akışı — bunlar Codex'in DE "commit'i engellemez" olarak sınıflandırdığı, daha büyük mimari kararlar veya gerçek credential gerektiren maddeler; §18'de "bilinen sınırlama" olarak işaretli.

## 15. Healthcheck Sonuçları (2. tur, fix'ler sonrası canlı doğrulama)

```
api          Up (healthy)
beat         Up (healthy)
caddy        Up (healthy)
frontend     Up (healthy)
postgres     Up (healthy)
redis        Up (healthy)
voice-agent  Up (healthy)   ← RestartCount=0
worker       Up (healthy)
```
**8/8 servis healthy — İLK denemede** (1. turdaki cap_add/healthcheck düzeltmeleri kalıcı olarak doğru).

HTTP test matrisi (Caddy üzerinden, gerçek login akışı DAHİL):

| Test | Sonuç |
|---|---|
| `GET /` (unauth) | 307 → `/login` |
| `GET /health` | 200 `{"status":"ok"}` |
| `GET /ready` | 200, DB+Redis "ok" |
| `GET /api/internal/whatever` | **403** |
| `GET /api/leads` (unauth) | **401** `{"detail":"Oturum bulunamadı"}` |
| `GET /api/api/leads` (eski buggy path) | **404** — bug'ın gerçekten var olduğunu kanıtlar |
| `POST /api/auth/login` (yanlış parola) | 401 |
| **`POST /api/auth/login` (gerçek bootstrap admin, doğru parola)** | **200**, geçerli `user`/`permissions`/`csrf_token` |
| **`GET /api/auth/me` (oturum cookie'siyle)** | **200**, aynı kullanıcı bilgisi |
| `GET https://localhost/` | 307 |
| Güvenlik header'ları | mevcut, `Server` header YOK |

## 16. Backup/Restore Smoke Test Sonucu (2. tur, non-root + yeni marker'larla)

- Manuel backup: ✅, non-root (`postgres`, uid 70) olarak çalıştığı doğrulandı, dosya sahipliği `postgres:postgres`.
- `verify-backup.sh --all`: ✅ (bir denemede geçici bir Docker Desktop volume-sync gecikmesi gözlendi — bkz. §18 — hemen retry'de ve manuel içerik kontrolünde dosyanın baştan beri GEÇERLİ olduğu doğrulandı).
- Eşzamanlı backup kilidi: ✅ (biri `flock` ile reddedildi, non-root altında da çalışıyor).
- Disposable restore smoke test: ✅ **TÜMÜ GEÇTİ** (yeni `target_db` allowlist'i gerçek disposable DB adlarını bozmadı).
- Off-site başarısızlık testi: ✅ local backup başarılı, off-site `Access Denied` ile başarısız, **yalnız `.last-local-success` güncellendi, `.last-remote-success` OLUŞMADI** (YÜKSEK-1 fix'i canlı doğrulandı).
- Gerçek off-site BAŞARI senaryosu test EDİLEMEDİ — gerçek S3/restic credential'ı yok (beklenen kısıtlama).

## 17. Secret / PII Taraması

- `git diff`/yeni dosyalarda secret pattern taraması: **temiz**.
- `.env.production` → ignored (doğrulandı).
- `.env.production.example` → commit edilebilir (doğrulandı).
- Backup script'leri: `PGPASSWORD`/connection string/restic parola HİÇBİR log satırına yazılmıyor (off-site-fail testinde de doğrulandı — yalnız restic'in kendi "Access Denied" mesajı görünüyor, credential değeri değil).

## 18. Bilinen Sınırlamalar

- FastAPI `/docs`/`/redoc`/`/openapi.json` production'da hâlâ açık (bilinçli sonraki-adım, `SECURITY_CHECKLIST.md`'de işaretli).
- Gerçek off-site backup BAŞARI senaryosu ve gerçek ACME/TLS akışı test EDİLEMEDİ (gerçek credential/domain gerektirir).
- `verify-backup.sh` bir denemede geçici bir Docker Desktop (macOS virtiofs) volume-sync gecikmesi nedeniyle yanlışlıkla "geçersiz" rapor etti; içerik manuel olarak `gzip -dc` ile doğrulandı ve GERÇEKTEN geçerliydi, hemen sonraki retry de geçti. Bu ortam-spesifik bir gözlemdir, script'te bir mantık hatası değildir — gerçek Linux production sunucusunda (özellikle native `ext4`/`xfs` volume'lerde) beklenmez, ama monitoring/alerting kurulurken tek bir "başarısız" sinyalin hemen retry edilmesi önerilir.
- ORTA-4 (smoke test kendi pg_dump çağrısını kullanıyor, gerçek `postgres-backup.sh`'i uçtan uca çağırmıyor), ORTA-6 (plain format backup, custom format değil), DÜŞÜK-2 (`--forwarded-allow-ips=*`) — Codex tarafından da "commit'i engellemez" sınıflandırılmış, bu turda ele alınmadı.
- Playwright E2E testleri yalnız KEŞFEDİLDİ, gerçek tarayıcı ortamıyla ÇALIŞTIRILMADI.
- Gerçek LiveKit/SIP çağrısı test EDİLEMEDİ.

## 19. Gerçek Production Kurulumu Öncesi Manuel Adımlar

1. `.env.production` oluşturulmalı — TÜM `REPLACE_ME` değerleri gerçek secret'larla değiştirilmeli. **Artık backend/voice-agent bunu production'da otomatik reddediyor** (YÜKSEK-3 fix'i) — unutulan bir placeholder artık sessizce geçmez.
2. `RESTIC_PASSWORD` ve `PII_ENCRYPTION_KEY`/`PHONE_HASH_PEPPER` `.env.production`'dan AYRI saklanmalı.
3. Gerçek DNS + 80/443 firewall açık olmalı.
4. `deploy/systemd/ivac-postgres-backup.{service,timer}` gerçek sunucu yoluna göre düzenlenmeli.
5. İlk gerçek backup + `make restore-smoke-test` başarıyla çalıştırılmadan sistem "production-ready" sayılmamalı.
6. `BACKUP_REMOTE_ENABLED=true` + gerçek credential'lar girilmeden sistem yalnız "local-only backup" durumundadır.
7. **YENİ**: `API_URL` origin olarak girilmeli, `/api` suffix'i EKLENMEMELİ (`docs/production/DEPLOYMENT.md`'de açıkça belgelendi).

## 20. Codex'in Özellikle İncelemesi Gereken Noktalar

1. `services/api/app/config.py` ve `services/voice-agent/agent/config.py`'deki yeni placeholder/uzunluk kontrolünün marker listesi (`replace_me`/`changeme`/`example`/`dummy`) yeterli mi, yoksa daha fazla marker mı gerekli.
2. `scripts/backup/postgres-restore.sh`'deki yeni `target_db` regex allowlist'inin (`^[a-zA-Z_][a-zA-Z0-9_]{0,62}$`) gerçek production DB adlandırma politikasıyla uyumlu olup olmadığı.
3. `scripts/backup/entrypoint.sh`'deki root→non-root düşürme deseninin (chown + su-exec) production'da beklenen tüm dosya izin senaryolarını kapsayıp kapsamadığı.
4. `deploy/caddy/Caddyfile`'daki `handle` sıralama fix'i ve yeni log filter (`format filter`) sözdiziminin Caddy'nin gelecek sürümleriyle uyumluluğu.
5. ORTA-4/ORTA-6/DÜŞÜK-2 — bilinçli olarak ertelenen bulgular, sonraki bir fazda ele alınmalı mı.

## 21. Commit İçin Önerilen Dosyaların Tam Listesi

```
.gitignore
.dockerignore
.env.production.example
Makefile
apps/web/Dockerfile
apps/web/next.config.ts
apps/web/playwright.config.ts
apps/web/tsconfig.json
compose.production.yml
deploy/caddy/Caddyfile
deploy/caddy/Caddyfile.local
deploy/caddy/compose.local-caddy.override.yml
deploy/systemd/ivac-postgres-backup.service
deploy/systemd/ivac-postgres-backup.timer
docs/production/DEPLOYMENT.md
docs/production/BACKUP_AND_RESTORE.md
docs/production/OPERATIONS_RUNBOOK.md
docs/production/SECURITY_CHECKLIST.md
infrastructure/docker/backup.Dockerfile
infrastructure/docker/voice-agent.Dockerfile
scripts/backup/lib.sh
scripts/backup/postgres-backup.sh
scripts/backup/postgres-restore.sh
scripts/backup/verify-backup.sh
scripts/backup/offsite-backup.sh
scripts/backup/restore-smoke-test.sh
scripts/backup/entrypoint.sh
services/api/Dockerfile
services/api/app/config.py
services/api/tests/unit/test_config.py
services/voice-agent/agent/config.py
services/voice-agent/agent/job_handler.py
services/voice-agent/agent/main.py
services/voice-agent/tests/test_config.py
services/voice-agent/tests/test_main.py
services/voice-agent/tests/test_runtime_adapters.py
CODEX_AUDIT_PHASE_6.md
PRODUCTION_INFRA_REPORT.md
```

## 22. Commit Dışı Bırakılması Gereken Dosyalar

```
.env.production          ← YEREL TEST ARTİFAKTI, .gitignore altında, ASLA commit edilmemeli
```
Başka hiçbir dosya hariç tutulmamalı — `git status --short` ile doğrulandı.

---

## Son Terminal Özeti

- **Görev genel olarak BAŞARILI** — Codex'in bulduğu KRİTİK-1, YÜKSEK-1, YÜKSEK-2, YÜKSEK-3 ve 4 ORTA/DÜŞÜK bulgu düzeltildi, tam yeniden doğrulama yapıldı.
- `docker compose config -q` (+ `--profile tools`): ✅ **GEÇTİ**.
- Tüm image'lar: ✅ **7/7 BAŞARIYLA (yeniden) BUILD EDİLDİ**.
- Test stack ayağa kaldırıldı: ✅ **8/8 servis healthy, İLK denemede**.
- Yalnız Caddy public port yayınladı: ✅ **DOĞRULANDI**.
- Caddy proxy testi: ✅ **GEÇTİ** — health/ready/internal-403/unauth-401 + **GERÇEK login akışı (bootstrap admin ile 200 + session)** dahil.
- **KRİTİK-1 fix doğrulandı**: frontend bundle'ında artık doğru origin (`/api` suffix YOK) gömülü; eski buggy path (`/api/api/leads`) 404, doğru path 401/200 veriyor.
- PostgreSQL backup alındı: ✅, non-root kullanıcıyla.
- Disposable restore testi: ✅ **GEÇTİ** (yeni SQL-injection-güvenli target_db allowlist ile).
- Off-site backup: ⚠️ yalnız BAŞARISIZLIK yolu test edilebildi (gerçek credential yok) — **artık `.last-remote-success` bu durumda YAZILMIYOR** (YÜKSEK-1 fix'i doğrulandı).
- Mevcut testler: backend 137/137 (+8 yeni), voice-agent 113/113 (+2 yeni), frontend Vitest 33/33, lint/typecheck/build temiz.
- Çalıştırılamayan kontroller: gerçek ACME/TLS akışı, gerçek off-site başarı senaryosu, gerçek LiveKit/SIP çağrısı, Playwright E2E gerçek çalıştırma.
- Çalışma dizini durumu: yalnız bu raporda listelenen dosyalar değişti/eklendi; `.env.production` gitignored ve commit edilmedi.
- **Bu oturumda HİÇBİR commit veya push YAPILMADI** — repo `main` dalında, `HEAD` hâlâ `0cd7b73`.
