# CODEX FINAL AUDIT PHASE 6

Tarih: 2026-07-19  
Rol: Üçüncü ve nihai bağımsız Codex denetimi  
Karar: **YELLOW — Kritik/yüksek kapalı, commit öncesi orta riskler düzeltilmeli**

## 1. Denetim kapsamı

Bu denetim `CLAUDE_FIX_PHASE_6_REAUDIT.md` raporundaki düzeltmeleri gerçek kod, gerçek diff ve önceki Codex raporları üzerinden doğrulamak için yapıldı. Production/test kodu değiştirilmedi, commit veya push yapılmadı. Yalnız bu rapor dosyası eklendi.

Kapsam: production compose/Docker/Caddy, backend config secret validation, backup/restore scriptleri, restic timeout, frontend API base URL, voice-agent health/lifecycle, kalite kapıları, secret/PII/artifact hijyeni.

## 2. Başlangıç git durumu

- Çalışma klasörü: `/Users/kadirugur/Projects/isletme-vitrini-ai-cagri`
- Branch: `main`
- HEAD: `0cd7b73f98d4c8b9e24227cdd25ae613b03bda0a`
- Beklenen HEAD `0cd7b73` ile uyumlu.
- Son commitler: `0cd7b73 feat: add secure AI call center management panel`, `03bfa9e feat: establish tested AI call center baseline`
- `git diff --check`: temiz.
- `git diff --summary`: boş.
- `.env.production`: tracked değil; `.gitignore:3:.env.*` ile ignored.
- Tracked env dosyaları: `.env.example`, `apps/web/.env.example`.
- Ignored artifact'lar mevcut: `.env.production`, `.pnpm-store/`, `.turbo/`, `.next/`, `node_modules/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `tests/e2e/.auth/`, `tests/e2e/test-results/`, `.DS_Store`.
- Beklenmeyen tracked secret/dump/cert artifact bulunmadı.

## 3. İncelenen raporlar ve dosyalar

İncelenen ana raporlar: `CODEX_AUDIT_PHASE_6.md`, `CODEX_REAUDIT_PHASE_6.md`, `CLAUDE_FIX_PHASE_6_REAUDIT.md`, `PRODUCTION_INFRA_REPORT.md`.

İncelenen ana dosyalar: `compose.production.yml`, `.env.production.example`, `.gitignore`, `Makefile`, `deploy/caddy/Caddyfile`, `deploy/caddy/Caddyfile.local`, `apps/web/Dockerfile`, `apps/web/lib/api/client.ts`, `apps/web/lib/api/client.test.ts`, `apps/web/lib/hooks/use-live-events.ts`, `services/api/Dockerfile`, `services/api/app/config.py`, `services/api/tests/unit/test_config.py`, `services/voice-agent/agent/config.py`, `services/voice-agent/agent/main.py`, `services/voice-agent/agent/job_handler.py`, `services/voice-agent/tests/*`, `infrastructure/docker/backup.Dockerfile`, `infrastructure/docker/voice-agent.Dockerfile`, `scripts/backup/*.sh`.

## 4. Önceki bulguların kapanış tablosu

| Bulgu | Önceki seviye | Claude'un düzeltmesi | Gerçek kod durumu | Yeniden test | Sonuç |
|---|---:|---|---|---|---|
| Frontend `/api/api` | Kritik | `API_URL` origin oldu, client trailing slash normalize ediyor | `.env.production.example` suffixsiz; `client.ts:51-54` slash kırpıyor | bundle grep temiz; Caddy `/api/api/leads` 404, doğru `/api/leads` 200 auth ile | KAPATILDI |
| Backend whitespace secret bypass | Yüksek | `str_strip_whitespace=True`, `.strip()`, marker normalize | `services/api/app/config.py:55-58`, `:172-200` doğru | 15 varyant + container whitespace-only fail-fast | KAPATILDI |
| Backup SIGPIPE false-fail | Yüksek | İçerik kontrol pipeline'ında lokal `set +o pipefail` | `postgres-backup.sh:79-82`, `verify-backup.sh:47-50` | 30/30 backup, 30/30 verify | KAPATILDI |
| Caddy Cookie/Authorization log sızıntısı | Yüksek | Header/query/Set-Cookie filter | `Caddyfile:104-119`, local dosyada aynı | gerçek Caddy validate/adapt + HTTPS log probe | KAPATILDI |
| Backend Ruff | Yüksek | Alembic lint hataları düzeltilmiş | `ruff check .` kapsamı alembic dahil | PASS | KAPATILDI |
| Backend MyPy | Yüksek | Kanonik `mypy app`; değişen test dosyası ayrı temiz | Makefile `typecheck` gerçekten `mypy app` | PASS; `mypy app tests/unit/test_config.py` PASS | KAPATILDI |
| Voice-agent MyPy çift modül | Yüksek | `tests/__init__.py` eklendi | Çift modül fatal hatası yok | `mypy agent` PASS; değişen 3 test dosyası PASS; geniş `mypy agent tests` 25 eski hata | KISMEN KAPATILDI |
| Restic sonsuz retry/hang | Yüksek | Her restic çağrısı `timeout` wrapper ile sarılmış | `offsite-backup.sh:40-46`, tüm restic çağrıları wrapper üzerinden | sahte endpoint `RESTIC_TIMEOUT_SECONDS=3` ile non-zero; süreç kesildi | KAPATILDI, orta timeout-env açığı var |
| Voice-agent healthcheck | Yüksek/orta | `--check-config` yerine SDK `GET /` | Dockerfile `:45-46` gerçek HTTP health | healthy -> LiveKit retry tükenince unhealthy; kill -> exited; restart -> healthy | KAPATILDI, operasyonel sınırlama var |
| Frontend trailing slash | Orta | `.replace(/\/+$/, "")` | `client.ts:51-54`, export hook'ta kullanılıyor | Vitest 35 passed, Caddy trailing slash 307 canonical | KAPATILDI |
| Restore SQL hardening | Orta | allowlist + `psql -v` + `dropdb/createdb --` | `postgres-restore.sh:85-88`, `:151-170` | smoke + 10 injection/guard test | KAPATILDI |

## 5. Backend secret doğrulaması

Durum: **KAPATILDI**.

- `str_strip_whitespace=True` aktif: `services/api/app/config.py:55-58`.
- `validate_runtime()` içinde ek `.strip()` var: `services/api/app/config.py:172`.
- Boş string, normal boşluk, 20+ boşluk, tab, newline, Unicode NBSP ve mixed whitespace reddedildi.
- ` REPLACE_ME `, `replace-me`, `replace_me`, `changeme`, `change-me`, `your-secret-here`, kısa secret reddedildi.
- Başında/sonunda whitespace bulunan geçerli uzun secret ve normal uzun güçlü test secret kabul edildi.
- Container düzeyinde `JWT_SECRET` whitespace-only override ile `RuntimeError: Production ortamında eksik zorunlu secret'lar: JWT_SECRET` verdi; secret değeri hata mesajında görünmedi.
- Production startup gerçek `get_settings()->validate_runtime()` yolundan geçiyor.

Yeni orta risk: marker kontrolü substring bazlı. `prefix-example-...` ve `prefix-dummy-...` gibi uzun güçlü değerler de reddedildi. Bu güvenlik açısından fail-closed, fakat gerçek random/passphrase değerlerde düşük olasılıklı yanlış pozitif üretebilir.

## 6. Backup SIGPIPE/false-fail doğrulaması

Durum: **KAPATILDI**.

- Kök neden doğru açıklanmış: `set -o pipefail` altında `gzip -dc | head -c 4096 | grep -q` upstream SIGPIPE yüzünden false-fail üretebiliyordu.
- Düzeltme sadece içerik akıl sağlığı pipeline'ında `pipefail` kapatıyor, sonra tekrar açıyor.
- Gerçek hatalar gizlenmiyor: boş/bozuk checksum restore smoke içinde reddedildi; remote failure non-zero verdi.
- 30 ardışık local backup: **30/30 başarılı**.
- `verify-backup.sh --all`: **30 backup tarandı, 0 başarısız**.
- Cleanup trap final exit code'u bozmadı.
- Dump/checksum eşleşmesi verify ile doğrulandı.

## 7. Restic timeout/hang doğrulaması

Durum: **KAPATILDI, ama orta risk açık**.

- `offsite-backup.sh:46`: `restic() { timeout "$RESTIC_TIMEOUT_SECONDS" restic "$@"; }`
- `snapshots`, `init`, `backup`, `check`, `forget --prune` çağrıları wrapper üzerinden geçiyor.
- `RESTIC_TIMEOUT_SECONDS=3` + unreachable/sahte S3 endpoint senaryosunda restic çağrıları `context canceled` ile kesildi ve global backup exit 1 oldu.
- `.last-remote-success` ve legacy `.last-success` oluşmadı; local dump korundu.
- Credential değerleri loglanmadı; hata mesajları yalnız endpoint ve restic hata sınıfını gösterdi.

**ORTA-1: `RESTIC_TIMEOUT_SECONDS=0` reddedilmiyor**

- Dosya/satır: `scripts/backup/offsite-backup.sh:40-46`
- Etki: Coreutils `timeout 0 <cmd>` komutu timeout uygulamadan child sürecin normal bitmesini bekliyor. Operatör env'i `0` yaparsa hang koruması sessizce devre dışı kalabilir.
- Doğrulama: backup image içinde `timeout 0 sh -c "sleep 0.2"` exit 0; `timeout -1` ve `timeout bad` exit 125.
- Durum: **AÇIK / ORTA**
- Minimum düzeltme: `RESTIC_TIMEOUT_SECONDS` için pozitif integer regex + `>0` kontrolü ekle; sıfır, negatif ve numeric olmayan değerleri script başında açık hata ile reddet.

## 8. Caddy log redaksiyonu

Durum: **KAPATILDI**.

- Gerçek `caddy:2-alpine caddy validate`: geçerli.
- `caddy adapt` çıktısında şu filter'lar derlendi: `request>headers>Authorization delete`, `request>headers>Cookie delete`, `request>uri query delete next/token/code/email/phone`, `resp_headers>Set-Cookie delete`.
- Canlı disposable HTTPS isteğinde sahte Authorization, Cookie/session, CSRF cookie, query token, email ve telefon değerleri access loglarda bulunmadı.
- Method/path/status gibi operasyonel bilgi kaldı; 25 log satırında operasyonel alanlar görüldü.
- Redaksiyon placeholder'ı en az bir Caddy reverse_proxy warning logunda `Cookie:["REDACTED"]` olarak görüldü. Normal access log filter'ı ise bazı alanları placeholder yerine tamamen siliyor; bu güvenli, ancak "her alan placeholder'la görünsün" beklentisi varsa davranış delete semantiğidir.

## 9. Backend kalite kapıları

Durum: **KAPATILDI**.

- Resmi Makefile Ruff komutu: `cd services/api && uv run ruff check .` -> PASS.
- Resmi Makefile MyPy komutu: `cd services/api && uv run mypy app` -> PASS, 81 source file.
- Ek değişen test kapsamı: `uv run mypy app tests/unit/test_config.py` -> PASS, 82 source file.
- Pytest: `153 passed, 3 warnings`.
- Warnings: Starlette/FastAPI TestClient/httpx ve `HTTP_422_UNPROCESSABLE_ENTITY` deprecation warning'leri; test fail değil.
- Config gevşetme veya kapsam daraltma tespit edilmedi; Makefile zaten `mypy app` kullanıyor, Claude'un önceki Codex `mypy app tests` farkı açıklaması teknik olarak doğru.

## 10. Voice-agent kalite kapıları

Durum: **KISMEN KAPATILDI**.

- `tests/__init__.py` çift-modül fatal MyPy hatasını çözüyor; import shadowing veya pytest discovery kaybı görülmedi.
- Ruff: `uv run ruff check agent tests` -> PASS.
- Kanonik MyPy: `uv run mypy agent` -> PASS, 16 source file.
- Bu turda değişen test dosyaları: `uv run mypy agent tests/test_config.py tests/test_runtime_adapters.py tests/test_main.py` -> PASS, 19 source file.
- Pytest: `113 passed`.
- Pickle/process regresyon testleri pytest içinde çalıştı.

Kalan orta risk: `uv run mypy agent tests` hâlâ 25 hata veriyor. Hatalar `test_logging_redaction.py`, `test_api_client.py`, `test_tools.py`, `test_job_handler.py`, `test_completion_guard.py` içinde; Claude bunları pre-existing test type debt olarak kapsam dışı bırakmış. Bu açıklama makul, fakat "tüm test paketi MyPy temiz" denemez.

## 11. Voice-agent health/lifecycle

Durum: **KAPATILDI, operasyonel sınırlamayla**.

- Dockerfile healthcheck artık `http://127.0.0.1:8081/` SDK endpoint'ine gerçek HTTP isteği yapıyor.
- LiveKit Agents SDK logları `HTTP server listening on :8081` gösterdi.
- Fake `LIVEKIT_URL=wss://example.invalid` ile ilk aşamada container healthy olabiliyor; bu, SDK retry hâlâ devam ederken endpoint'in 200 dönmesi anlamına geliyor.
- `max_retry=16` tükendikten sonra container `running/unhealthy` durumuna düştü; health dış bağlantı kalıcı başarısızlığını sonunda yakalıyor.
- Ana süreç `SIGKILL` ile öldürüldü: container `exited`, exit 137, health `unhealthy`.
- `docker compose up -d voice-agent` sonrası yeni process `running/healthy` oldu; eski state yeni başlangıcı etkilemedi.

Sonuç: `8/8 healthy` yalnız worker HTTP server'ının ayakta olduğunu ve LiveKit bağlantısının henüz kalıcı başarısız sayılmadığını kanıtlar. Gerçek LiveKit'e bağlı ve iş alıyor anlamına tek başına gelmez. Gerçek credential ile uçtan uca bağlantı testi production açılışı öncesi operasyonel blokerdir.

## 12. Frontend API ve trailing slash

Durum: **KAPATILDI**.

- `API_BASE_URL` build-time origin'i trailing slash'lardan arındırıyor: `apps/web/lib/api/client.ts:51-54`.
- `use-live-events.ts` aynı exported `API_BASE_URL` değerini kullanıyor.
- Vitest: 35/35 passed; yeni iki trailing slash testi geçti.
- Production bundle grep: `/api/api`, Docker internal hostname, `localhost:8000`, placeholder secret veya yanlış origin bulunmadı.
- Caddy üzerinden:
  - `/` -> 307 `/login?next=%2F`
  - `/health` -> 200 JSON
  - `/ready` -> 200 JSON
  - `/api/internal/probe` -> 403
  - unauth `/api/leads` -> 401 JSON
  - login -> 200 JSON
  - authenticated `/api/auth/me` -> 200 JSON
  - authenticated `/api/leads` -> 200 JSON
  - `/api/api/leads` -> 404 JSON
  - `/api/leads/` -> 307 canonical `/api/leads`
  - `/api/live/events` -> 200 `text/event-stream`

API hata cevapları frontend HTML'e dönüşmedi.

## 13. Restore güvenliği

Durum: **KAPATILDI**.

- `target_db` SQL string içine ham gömülmüyor; allowlist `^[a-zA-Z_][a-zA-Z0-9_]{0,62}$` var.
- Existence check `psql -v target_db=... "datname = :'target_db'"` kullanıyor.
- Drop/create `dropdb --if-exists -- "$target_db"` ve `createdb -- "$target_db"` ile ayrı argümanlar üzerinden yapılıyor.
- Backup format plain SQL olduğu için restore `pg_restore` değil `gzip -dc | psql -v ON_ERROR_STOP=1 -d "$target_db"` kullanıyor. Bu önceki plain-format sınırlamasıyla tutarlı.
- `--option`, shell metacharacter, newline, quote, slash, boş değer ve production DB adı guard testleri geçti: 10/10 reddedildi.
- Checksum doğrulanmadan destructive işlem başlamıyor; corrupt checksum smoke içinde reddedildi.
- Production database overwrite koruması devam ediyor.
- Parola argv/log içine konmuyor; libpq env kullanılıyor.

## 14. Docker/Compose/public port

Durum: **KAPATILDI**.

- `docker compose config -q`: PASS.
- `--profile tools config -q`: PASS.
- Normal servisler: 8 (`postgres`, `redis`, `beat`, `api`, `frontend`, `caddy`, `voice-agent`, `worker`).
- Tools profili: 10 (`migrate`, `backup` dahil).
- No-cache build: 7/7 image başarıyla build edildi. Buildx plugin yok uyarısı nedeniyle klasik builder kullanıldı; `--no-cache` ile katmanlar yeniden işlendi.
- Disposable stack: 8/8 healthy görüldü; sonra fake LiveKit retry tükenince voice-agent intentionally unhealthy oldu.
- Production compose portları: yalnız Caddy 80/tcp, 443/tcp, 443/udp publish ediyor. Local override testinde ek olarak 8080/tcp vardı; bu production dosyasında yok.
- Postgres/Redis/API/frontend/worker/beat/voice-agent host port publish etmiyor.
- Backup gerçek entrypoint ile `uid=70(postgres)` olarak çalıştı; backup dosyaları `postgres:postgres`.
- Disposable Docker project ve volumes test sonunda kaldırıldı.

## 15. Backup/restore stres sonuçları

- Local backup stress: **30/30 başarılı**.
- Verify: **30/30 geçerli**, 0 başarısız.
- Concurrent lock: 3 paralel backup'ta 1 başarı, 2 doğru `flock` reddi.
- Remote disabled: exit 0, `.last-local-success` var, `.last-remote-success` yok.
- Remote enabled + credential eksik: exit 1, remote/global marker yok.
- Remote enabled + sahte upload failure: exit 1, timeout ile sınırlı, remote/global marker yok.
- Retention: 20 gün eski disposable fixture dosyası silindi; exit 0.
- Restore smoke: tüm adımlar geçti, corrupt checksum doğru reddedildi.
- Restore injection/guard: 10/10 reddedildi.

## 16. Full test sonuçları

Backend:
- Ruff: PASS.
- MyPy: PASS (`mypy app`, 81 file).
- Pytest: `153 passed, 3 warnings`.

Voice-agent:
- Ruff: PASS.
- MyPy canonical: PASS (`mypy agent`, 16 file).
- MyPy changed tests: PASS (`agent` + 3 test file, 19 file).
- MyPy broad: FAIL (`mypy agent tests`, 25 errors in 5 old test files).
- Pytest: `113 passed`.

Frontend:
- Lint: PASS.
- Typecheck: PASS.
- Vitest: `35 passed`.
- Production build: PASS, 19 routes.

Root workspace:
- `pnpm exec turbo run lint typecheck build --force`: 3/3 successful, 0 cached.
- Playwright discovery: 23 tests in 4 files.
- Full Playwright run yapılmadı; bu denetimde Caddy/login/API flow curl ile doğrulandı.

Production:
- Compose config normal/tools: PASS.
- 7/7 no-cache build: PASS.
- 8 servis startup/health: PASS, voice-agent external failure sonrası unhealthy davranışı ayrıca doğrulandı.
- Public port izolasyonu: PASS.
- Caddy/login/API: PASS.
- Backup/restore/remote failure/timeout/lock: PASS, `RESTIC_TIMEOUT_SECONDS=0` hariç.

## 17. Secret/PII/artifact taraması

- `git diff --check`: temiz.
- `git status --short`: beklenen Aşama 6 dosyaları + raporlar.
- `git status --short --ignored`: `.env.production`, caches, `.next`, `.pnpm-store`, `.venv`, coverage ve test artifacts ignored.
- `git ls-files '*.env*'`: yalnız `.env.example`, `apps/web/.env.example`.
- `git check-ignore -v .env.production`: `.gitignore:3:.env.*`.
- High-confidence secret pattern filename taramasında eşleşmeler eski audit dokümanları ve test redaction dosyalarında kaldı; gerçek secret değeri rapora kopyalanmadı.
- PII pattern filename taraması example/test/audit bağlamlarında eşleşti; gerçek lead dump, transcript veya audio artifact bulunmadı.
- Frontend bundle grep temiz.
- Docker image history (`api`, `frontend`, `voice-agent`) secret/token/password marker eşleşmesi vermedi.
- Disposable `/tmp` env/log dosyaları ve `ivac-final-audit` Docker container/volume kaynakları temizlendi.

## 18. Yeni regresyonlar

### ORTA-1: `RESTIC_TIMEOUT_SECONDS=0` timeout korumasını devre dışı bırakıyor

- Dosya/satır: `scripts/backup/offsite-backup.sh:40-46`
- Etki: Yanlış env değeri restic hang korumasını sessizce kapatabilir.
- Doğrulama: `timeout 0 sleep` exit 0; sıfır değer script tarafından reddedilmiyor.
- Durum: **AÇIK**
- Minimum düzeltme: pozitif integer validasyonu ekle.

### ORTA-2: Placeholder marker substring false-positive üretebilir

- Dosya/satır: `services/api/app/config.py:36-43`, `:190-200`; `services/voice-agent/agent/config.py:20-27`, `:139-146`
- Etki: İçinde `example` veya `dummy` geçen güçlü bir secret production'da reddedilir.
- Doğrulama: uzun `prefix-example-...` ve `prefix-dummy-...` test değerleri reddedildi.
- Durum: **AÇIK / düşük olasılıklı operasyonel sürtünme**
- Minimum düzeltme: marker eşleşmesini tam canonical değer veya bilinen placeholder kalıplarıyla sınırlamak.

### ORTA-3: Geniş voice-agent test MyPy hâlâ temiz değil

- Dosya/satır: `services/voice-agent/tests/test_logging_redaction.py`, `test_api_client.py`, `test_tools.py`, `test_job_handler.py`, `test_completion_guard.py`
- Etki: Production `agent` kodu MyPy temiz, pytest temiz; fakat test paketi tip hijyeni eksik kalıyor.
- Doğrulama: `uv run mypy agent tests` -> 25 errors.
- Durum: **AÇIK**
- Minimum düzeltme: ayrı test typing cleanup fazı.

## 19. Açık kalan bulgular

Kritik açık: **yok**.  
Yüksek açık: **yok**.

Orta açık:
- `RESTIC_TIMEOUT_SECONDS=0` reddedilmiyor.
- Placeholder marker substring false-positive riski.
- Geniş voice-agent test MyPy borcu.

Operasyonel açık:
- Gerçek off-site repository credential ile başarılı upload ve restore doğrulanmadı.
- Gerçek LiveKit/OpenAI/Netgsm credential ile uçtan uca bağlantı/çağrı doğrulanmadı.
- Gerçek ACME/TLS domain akışı doğrulanmadı.
- Alerting/monitoring canlı ortamda kurulup doğrulanmadı.

## 20. Commit kapsamına alınması gereken dosyalar

Bu haliyle YELLOW olduğu için önce orta risklerin düzeltilmesi önerilir. Düzeltme sonrası commit kapsamı:

`.gitignore`, `.dockerignore`, `.env.production.example`, `Makefile`, `compose.production.yml`, `apps/web/Dockerfile`, `apps/web/lib/api/client.ts`, `apps/web/lib/api/client.test.ts`, `apps/web/next.config.ts`, `apps/web/playwright.config.ts`, `apps/web/tsconfig.json`, `deploy/`, `docs/production/`, `infrastructure/docker/backup.Dockerfile`, `infrastructure/docker/voice-agent.Dockerfile`, `scripts/backup/`, `services/api/Dockerfile`, `services/api/alembic/`, `services/api/app/config.py`, `services/api/tests/unit/test_config.py`, `services/voice-agent/agent/config.py`, `services/voice-agent/agent/job_handler.py`, `services/voice-agent/agent/main.py`, `services/voice-agent/tests/__init__.py`, `services/voice-agent/tests/test_config.py`, `services/voice-agent/tests/test_main.py`, `services/voice-agent/tests/test_runtime_adapters.py`, `CODEX_AUDIT_PHASE_6.md`, `CODEX_REAUDIT_PHASE_6.md`, `PRODUCTION_INFRA_REPORT.md`, `CLAUDE_FIX_PHASE_6_REAUDIT.md`, `CODEX_FINAL_AUDIT_PHASE_6.md`.

## 21. Commit dışında bırakılması gereken dosyalar

Kesinlikle commit dışı:

`.env.production`, `.pnpm-store/`, `.next/`, `.turbo/`, `node_modules/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `tests/e2e/.auth/`, `tests/e2e/test-results/`, `.DS_Store`, Caddy state/certs, Docker volumes, backup dump/checksum dosyaları, gerçek credential içeren her dosya.

## 22. Production açılışı öncesi operasyonel engeller

- Gerçek off-site backup repository credential ile başarılı restic upload, `restic check`, retention ve restore drill yapılmadan disaster recovery hazır kabul edilmemeli.
- Gerçek LiveKit/OpenAI/Netgsm credential ile worker bağlantısı ve test çağrı lifecycle doğrulanmalı; bugünkü fake endpoint testi yalnız failure behavior'ı kanıtladı.
- Gerçek domain/ACME/TLS akışı doğrulanmalı.
- Alerting `.last-local-success` ve `.last-remote-success` ayrımını doğru izleyecek şekilde kurulmalı.
- `RESTIC_TIMEOUT_SECONDS` pozitif integer olarak fail-fast validate edilmeli.

## 23. Nihai karar

**YELLOW — Kritik/yüksek kapalı ama commit öncesi orta risk düzeltilmeli.**

Kodun ana production riskleri önceki RED durumundan çıkmış görünüyor: backend whitespace secret bypass kapandı, backup false-fail kapanmış, Caddy Cookie/Authorization redaksiyonu çalışıyor, frontend `/api/api` ve trailing slash sorunu kapanmış, restore injection hardening tamamlanmış, no-cache production build ve disposable stack testi geçti.

Yine de commit öncesi `RESTIC_TIMEOUT_SECONDS=0` açığı kapatılmalı. Geniş voice-agent test MyPy borcu ve placeholder false-positive davranışı da aynı commit öncesi veya hemen sonraki ayrı hijyen işi olarak ele alınmalı. Production açılışı ise gerçek off-site başarı testi ve gerçek dış servis credential doğrulamaları yapılmadan başlamamalı.

