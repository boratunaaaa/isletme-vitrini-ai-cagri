# CODEX REAUDIT PHASE 6

Tarih: 2026-07-18  
Rol: Bağımsız production altyapı yeniden denetimi  
Karar: **RED — Kritik/yüksek sorun açık, commit edilmemeli**

## 1. Yeniden denetim kapsamı

Bu denetim, `CODEX_AUDIT_PHASE_6.md` sonrası Claude tarafından bildirilen düzeltmeleri bağımsız olarak doğrulamak için yapıldı. Production/test kodu değiştirilmedi. Commit/push yapılmadı. Yalnız bu rapor dosyası eklendi.

## 2. Başlangıç git durumu

- Branch: `main`
- HEAD: `0cd7b73f98d4c8b9e24227cdd25ae613b03bda0a` (`0cd7b73` beklentisi doğru)
- Son commit: `0cd7b73 feat: add secure AI call center management panel`
- Commit/push: Denetim sırasında yapılmadı.
- `git diff --check`: temiz.
- Değişiklikler: Aşama 6 production infra kapsamındaki dosyalar ağırlıklı; ek olarak mevcut ignored artifact'lar var.
- `.pnpm-store/`: çalışma ağacında ignored olarak mevcut, commit kapsamına girmiyor.
- Mevcut raporlar: `CODEX_AUDIT_PHASE_6.md` ve `PRODUCTION_INFRA_REPORT.md` mevcut.

## 3. İncelenen dosyalar

Ana dosyalar: `.env.production.example`, `compose.production.yml`, `apps/web/lib/api/client.ts`, `apps/web/lib/hooks/use-live-events.ts`, `apps/web/Dockerfile`, `deploy/caddy/Caddyfile`, `deploy/caddy/Caddyfile.local`, `scripts/backup/*.sh`, `infrastructure/docker/backup.Dockerfile`, `services/api/app/config.py`, `services/voice-agent/agent/config.py`, `services/voice-agent/agent/job_handler.py`, `services/voice-agent/agent/main.py`, ilgili testler ve güncel git diff.

## 4. Önceki bulguların kapanış tablosu

| Bulgu | Önceki seviye | Claude iddiası | Gerçek kod durumu | Test kanıtı | Sonuç |
| --- | --- | --- | --- | --- | --- |
| KRITIK-1 Frontend API URL `/api/api` | Kritik | Kapatıldı | `.env.production.example:20-27` origin kullanıyor, `compose.production.yml:333-337` build arg geçiriyor, bundle içinde `/api/api`/internal hostname bulunmadı. | Production image build + bundle grep + Caddy login/API testleri. | **KAPATILDI**, yeni trailing slash orta riski var. |
| YUKSEK-1 Off-site başarısızken `.last-success` | Yüksek | Kapatıldı | `scripts/backup/postgres-backup.sh:93-115` local/remote marker'ları ayırıyor, `.last-success` yazmıyor. | Remote disabled, credential missing, fake restic failure testleri. | **KAPATILDI**, ancak backup scriptinde yeni yüksek güvenilirlik regresyonu var. |
| YUKSEK-2 Restore DB adı injection | Yüksek | Kapatıldı | `scripts/backup/postgres-restore.sh:85-88` allowlist var; zararlı adlar reddediliyor. Ancak `psql -c "DROP DATABASE \"${target_db}\""` ve `SELECT ... '${target_db}'` SQL interpolation hâlâ var (`:141-156`). | Zararlı ad testleri ve bozuk checksum testi geçti. | **KISMEN KAPATILDI**: injection pratikte allowlist ile kapanmış, implementation beklentisi tam karşılanmamış. |
| YUKSEK-3 Placeholder secret fail-fast | Yüksek | Kapatıldı | Voice-agent normalize ediyor (`services/voice-agent/agent/config.py:21-27`), backend etmiyor (`services/api/app/config.py:149-151`). 20+ whitespace secret backend production'da geçiyor. | Ad-hoc variant testleri; container placeholder `REPLACE_ME` fail-fast geçti. | **AÇIK**. |

## 5. Kritik-1 frontend API URL doğrulaması

Durum: Önceki kritik ana senaryo kapanmış.

- `.env.production.example:21-27` artık `API_URL=https://panel.example.com` ve `/api` suffix eklemeyin notu içeriyor.
- `compose.production.yml:333-337` `API_URL` değerini `NEXT_PUBLIC_API_URL` build arg olarak frontend image'a geçiriyor.
- `apps/web/Dockerfile:31-37` `NEXT_PUBLIC_API_URL` değerini build aşamasında gömüyor.
- Production bundle grep sonucu: `/api/api`, `http://backend`, `http://api`, `localhost:8000`, `api.example.invalid`, yanlış panel-domain `/api` suffix'i bulunmadı.
- Caddy üzerinden `/api/auth/login` 200, `/api/auth/me` 200, `/api/leads` 200, `/api/api/leads` 404 döndü.

Yeni bulgu:

- Seviye: **ORTA**
- Dosya/satır: `apps/web/lib/api/client.ts:46-67`, `apps/web/lib/hooks/use-live-events.ts:79`
- Etki: `API_URL=https://panel.example.com/` gibi trailing slash ile build edilirse URL string concat `https://panel.example.com//api/...` üretir. Caddy `path /api/*` matcher'ı için bu riskli bir production misconfig senaryosu.
- Doğrulama: Node URL testi `https://panel.example.com/ + /api/leads => https://panel.example.com//api/leads`.
- Durum: **YENİ REGRESYON/RISK**
- Minimum öneri: Frontend base URL build-time normalize edilmeli (`replace(/\/+$/, "")`) ve env validator trailing slash reddetmeli.

## 6. Yüksek-1 backup başarı semantiği

Durum: Önceki `.last-success` semantiği kapanmış.

- `.last-local-success`: local dump/checksum/retention sonrası yazılıyor (`scripts/backup/postgres-backup.sh:93-100`).
- `.last-remote-success`: off-site upload ve restic check/retention sonrası yazılıyor (`:104-113`).
- `.last-success`: artık yazılmıyor.
- Remote disabled test: exit 0, `.last-local-success` güncellendi, `.last-remote-success` yok, `.last-success` yok.
- Remote enabled + credential missing: exit 1, remote/global marker değişmedi.
- Remote enabled + fake failure: exit 1, remote/global marker değişmedi.

Yeni bulgu:

- Seviye: **YÜKSEK**
- Dosya/satır: `scripts/backup/postgres-backup.sh:68`
- Etki: İçerik kontrolü `set -o pipefail` altında `gzip -dc "$tmp_path" | head -c 4096 | grep -q ...` kullanıyor. `grep -q` erken çıkışı ve `head/gzip` SIGPIPE etkileşimi nedeniyle geçerli dump aralıklı olarak "pg_dump çıktısına benzemiyor" hatasıyla başarısız olabiliyor. Production backup periyodik olarak false negative ile kaçabilir.
- Doğrulama: Aynı disposable DB'de 5 local backup denemesinden biri exit 1 verdi: `run_3=1 Backup içeriği pg_dump çıktısına benzemiyor`.
- Kapanış durumu: **YENİ REGRESYON**
- Minimum öneri: İlk 4096 byte'ı değişkene/temp dosyaya alıp tek komutla grep etmek veya pipeline'ı `pipefail`/SIGPIPE etkisinden ayırmak.

Ek not: Marker dosyaları `date > file` ile yazılıyor (`:100`, `:113`); bu atomik değil. Timestamp kısa olduğu için etkisi daha düşük, ama istenen atomik durum dosyası davranışı tam sağlanmıyor.

## 7. Yüksek-2 restore database adı güvenliği

Durum: Pratik injection riski büyük ölçüde kapanmış, implementation beklentisi tam karşılanmamış.

- Allowlist: `^[a-zA-Z_][a-zA-Z0-9_]{0,62}$` (`scripts/backup/postgres-restore.sh:85-88`).
- Boş değer, `--maintenance-db`, slash/path, newline, quote, backtick, `$(...)`, semicolon değerleri destructive işlemden önce reddedildi.
- Bozuk checksum testinde `ivac_bad_checksum_reaudit` DB oluşturulmadı.
- Normal disposable restore geçti; gerçek production backup dosyasından disposable DB'ye restore 23 public table ile tamamlandı.

Kalan risk:

- Seviye: **ORTA**
- Dosya/satır: `scripts/backup/postgres-restore.sh:141-156`
- Etki: Kod hâlâ SQL string interpolation kullanıyor. Allowlist bunu pratikte güvenli hale getiriyor, fakat önceki denetimin "SQL içine interpolation yapma, dropdb/createdb argümanları kullan" beklentisi tam karşılanmadı.
- Doğrulama: Kaynak kod incelemesi + zararlı DB adı testleri.
- Kapanış durumu: **KISMEN KAPATILDI**
- Minimum öneri: `dropdb --if-exists -- "$target_db"`, `createdb -- "$target_db"` ve parametreli/quote-safe existence check kullan.

## 8. Yüksek-3 placeholder secret validasyonu

Durum: **AÇIK**.

- Seviye: **YÜKSEK**
- Dosya/satır: `services/api/app/config.py:149-151`
- Etki: Backend production secret değerleri strip/normalize edilmiyor. 25 boşluk karakterinden oluşan `JWT_SECRET` production `validate_runtime()` içinden geçti. Bu, "dolu ama gerçek secret olmayan" değerle backend startup'ın production'da geçebilmesi anlamına gelir.
- Doğrulama: Backend ad-hoc variant testi: `REPLACE_ME`, `replace_me`, `changeme`, `CHANGE_ME`, `your-secret-here`, kısa değer ve kısa whitespace reddedildi; 20+ whitespace **PASS** verdi. Voice-agent aynı 20+ whitespace değeri reddetti.
- Kapanış durumu: **AÇIK**
- Minimum öneri: Backend `SettingsConfigDict(str_strip_whitespace=True)` veya runtime'da `value = getattr(...).strip()`; whitespace-only değeri missing/weak sayan test ekle.

Container startup:

- `.env.production.example` placeholder'ları API ve voice-agent container config check seviyesinde fail-fast tetikledi.
- Hata mesajları secret değerlerini basmadı.

## 9. Orta/düşük düzeltmelerin doğrulaması

- `.pnpm-store`: `.gitignore:11-18` altında ignore ediliyor; `git status --ignored` içinde `!! .pnpm-store/`, commit kapsamına girmiyor. Kapanmış.
- Caddy log redaksiyonu: Query parametreleri için filter var (`deploy/caddy/Caddyfile:102-115`), Caddy adapt çıktısında `request>uri query delete next/token/code/email/phone` görüldü. Ancak `Cookie` ve `Authorization` header redaksiyonu yok. Bu önceki ORTA-2'yi tam kapatmıyor.
- Backup container non-root: Runtime komutları `uid=70(postgres)` ile çalıştı; `/backups` dosyaları `postgres:postgres`. Ancak entrypoint root başlayıp ownership düzeltip sonra düşüyor (`infrastructure/docker/backup.Dockerfile:20-24`, `compose.production.yml:413-424`). Kabul edilebilir, ama "tamamen root'suz" değil.
- Dokümantasyon/Caddy uyarıları: Caddy validate gerekli env ile geçiyor; hâlâ `Caddyfile input is not formatted` uyarısı var (`deploy/caddy/Caddyfile:18` civarı).

Yeni Caddy bulgusu:

- Seviye: **YÜKSEK**
- Dosya/satır: `deploy/caddy/Caddyfile:102-115`
- Etki: Access log filter yalnız query string alanını siliyor. Default JSON access log request headers objesini içeriyor; `Cookie` ve `Authorization` için delete kuralı yok. Session cookie veya bearer token içeren istekler access log'a düşebilir.
- Doğrulama: `caddy adapt` çıktısında yalnız `request>uri query` actions görüldü; header redaksiyon action'ı yok. Runtime loglarda request `headers` objesi basılıyor.
- Kapanış durumu: **YENİ REGRESYON / ÖNCEKİ ORTA-2 TAM KAPANMADI**
- Minimum öneri: `request>headers>Cookie`, `request>headers>Authorization`, gerekiyorsa `Set-Cookie` response header'ları filter ile silinmeli veya access log header alanı daraltılmalı.

## 10. Ertelenmiş bulguların değerlendirmesi

- ORTA-4: `restore-smoke-test.sh` kendi mini dump'ını üretiyor; gerçek production backup scriptini tam temsil etmiyor. Erteleme anlaşılır, commit'i tek başına engellemez; ama bu denetimde gerçek backup scriptinde yüksek regresyon bulunduğu için risk artık teorik değil.
- ORTA-6: Plain SQL backup formatı kullanılıyor. Restore çalışıyor, `pg_restore --list` uygulanamaz. Geçici kabul edilebilir, production açılışını tek başına engellemez; custom format uzun vadede daha iyi.
- DUSUK-2: `--forwarded-allow-ips=*` API Dockerfile CMD içinde duruyor. Caddy tek giriş noktası ve backend host port publish yoksa geçici kabul edilebilir; public exposure yok.
- DUSUK-3: Full stack yeniden test edildi; 7/7 build ve 8/8 healthy üretildi, ama voice-agent health fake LiveKit URL ile de healthy görünebildiği için operasyonel health sinyali sınırlı.

Numaralandırma notu: Önceki Codex raporu ile Claude raporundaki ertelenmiş madde numaraları birebir semantik olarak aynı kullanılmalı; mevcut raporda bazı başlıklar "ertelendi" olarak doğru görünse de DUSUK-3 artık bu denetimde tekrarlandı.

## 11. Voice-agent pickle/process değerlendirmesi

- Entry point modül seviyesinde: `services/voice-agent/agent/job_handler.py:483-507`.
- `build_server()` entrypoint'i doğrudan kaydediyor (`:510-517`).
- Import sırasında dış servis bağlantısı başlamıyor; bağlantı `run_worker()` sonrasında başlıyor (`:520-523`, `services/voice-agent/agent/main.py:42-48`).
- Container pickle testi geçti: `agent.job_handler entrypoint True`.
- Child process import testi geçti.
- Spawn smoke exit 0 verdi, ancak `coroutine 'entrypoint' was never awaited` uyarısı üretti; bu test gerçek LiveKit job lifecycle'ını çalıştırmıyor, yalnız callable resolution/pickle yönünü kanıtlıyor.
- Voice-agent pytest: `113 passed`.

Değerlendirme: Pickle/local function düzeltmesi kabul edilebilir. Process-pool smoke hâlâ lifecycle açısından sınırlı; production açılışı için gerçek LiveKit credential ile worker bağlantısı ayrıca doğrulanmalı.

## 12. Docker/Compose değerlendirmesi

- Production compose config geçti.
- Tools profile config geçti.
- 7/7 image build üretildi; klasik Docker builder cache kısmen kullanıldı, frontend production `next build` tekrar çalıştı.
- 8/8 servis `healthy` görüldü.
- Production compose port config: yalnız `caddy` 80/tcp, 443/tcp, 443/udp publish ediyor; postgres/redis/api/frontend/worker/beat/voice-agent host port publish etmiyor.
- Local test override ayrıca 8080 publish ediyor; bu yalnız disposable test içindi.
- Disposable project temizlendi; kalan test volume'u ayrıca kaldırıldı.

Risk:

- Voice-agent fake LiveKit URL ile connection retry/failure yaşarken compose health `healthy` görünebiliyor. Healthcheck config-only olduğu için 8/8 healthy gerçek dış servis hazır anlamına gelmiyor.

## 13. Caddy/TLS/proxy değerlendirmesi

- Production Caddyfile gerekli env ile validate geçti.
- `caddy adapt` route sırası doğru: `/api/internal/*` 403, `/health`/`/ready` backend, `/api/*` backend, kalan frontend.
- `caddy validate` hâlâ format uyarısı veriyor.
- HTTP testleri local TLS/Caddy üzerinden:
  - `/`: 307 `/login?next=%2F`
  - `/login`: 200 HTML
  - `/health`: 200 JSON
  - `/ready`: 200 JSON
  - `/api/internal/probe`: 403
  - unauth `/api/leads`: 401 JSON
  - login: 200 session
  - auth `/api/auth/me`: 200
  - auth `/api/leads`: 200 JSON
  - `/api/api/leads`: 404 JSON
  - `/api/live/events`: 200 `text/event-stream`
- `localhost` IPv6 `::1` bağlantısı bazı curl denemelerinde refused; `curl -4` ile stabil çalıştı. Bu local binding/test detayıdır.

## 14. Backup/restore değerlendirmesi

- Local backup geçti; checksum ve gzip doğrulama geçti.
- `verify-backup.sh --all` geçti.
- PostgreSQL client/server major uyumu: `pg_dump 16.14`, server `16.14`.
- Concurrent lock: Kesilen restic denemesi lock'u tuttu; ikinci backup denemeleri "Başka bir backup zaten çalışıyor" ile exit 1 verdi. Container durdurulunca lock serbest kaldı. Lock çalışıyor.
- Remote disabled: exit 0, local marker yazıldı, remote/global marker yok.
- Remote credential missing: exit 1, remote/global marker değişmedi.
- Fake remote failure: exit 1, remote/global marker değişmedi.
- Restore smoke: geçti.
- Bozuk checksum: restore reddedildi, DB oluşturulmadı.
- Zararlı DB adları: destructive işlemden önce reddedildi, injection yan etkisi oluşmadı.
- Gerçek production backup scriptinin ürettiği dosyadan disposable restore: geçti.

Bloklayıcı: `postgres-backup.sh:68` aralıklı false-fail üretiyor; bu yüksek seviye yeni regresyondur.

## 15. Test sonuçları

- Backend Ruff: **FAIL**. Alembic import sorting, unused import ve line length dahil 10 hata.
- Backend MyPy: **FAIL**. `uv run mypy app tests` 89 hata verdi; çoğu testlerde eksik type annotation, ayrıca birkaç `arg-type`/`union-attr` hatası var.
- Backend pytest: `137 passed, 3 warnings`.
- Voice-agent Ruff: PASS.
- Voice-agent MyPy: **FAIL**. `tests/factories.py` iki modül adıyla bulunuyor: `factories` ve `tests.factories`.
- Voice-agent pytest: `113 passed`.
- Frontend lint: PASS.
- Frontend typecheck: PASS.
- Frontend Vitest: `33 passed`.
- Frontend production build: PASS.
- Root `pnpm lint/typecheck/build`: PASS, fakat turbo cache replay kullandı; bağımsız web komutları ayrıca çalıştırıldı.
- Playwright discovery: 23 test listelendi. Full Playwright koşulmadı; mevcut config production stack yerine Next dev server readiness'i başlatıyor/bekliyor ve storageState artifact yazıyor. Production akış Caddy üzerinden curl ile doğrulandı.

## 16. Full stack health ve HTTP sonuçları

- Disposable stack project: `ivac-reaudit-phase6`.
- Migrate geçti.
- Bootstrap admin disposable test kullanıcısı ile geçti.
- `docker compose ps`: 8/8 healthy.
- Caddy HTTP/TLS sonuçları 13. bölümde listelendi.
- Test sonunda disposable container/network/volume kaynakları temizlendi.

## 17. Secret/PII/artifact taraması

- `git diff --check`: temiz.
- Tracked env dosyaları: `.env.example`, `apps/web/.env.example`.
- `.env.production`: ignored ve çalışma ağacında mevcut. Değerleri okunup rapora basılmadı; commit kapsamına girmiyor.
- `.pnpm-store/`, `.next/`, cache, `.auth/`, test-results: ignored artifact olarak mevcut.
- Frontend Docker image history: secret/token/password/internal URL eşleşmesi yok.
- Frontend production bundle grep: `/api/api`, internal Docker hostname, placeholder secret marker bulunmadı.
- Repo taramasında secret kelime eşleşmeleri çoğunlukla env değişken adı, example, test veya dokümantasyon bağlamında. Gerçek secret değeri rapora yazılmadı.

## 18. Yeni bulunan regresyonlar

1. **YÜKSEK — Backup false-fail regresyonu**  
   Dosya/satır: `scripts/backup/postgres-backup.sh:68`  
   Etki: Geçerli backup aralıklı olarak başarısız sayılıyor.  
   Doğrulama: 5 denemede 1 false-fail.  
   Durum: Açık.

2. **YÜKSEK — Backend whitespace-only production secret kabulü**  
   Dosya/satır: `services/api/app/config.py:149-151`  
   Etki: 20+ boşluk karakterinden oluşan secret production startup'ı geçebilir.  
   Doğrulama: Ad-hoc variant testi.  
   Durum: Açık.

3. **YÜKSEK — Caddy Cookie/Authorization header redaksiyonu yok**  
   Dosya/satır: `deploy/caddy/Caddyfile:102-115`  
   Etki: Session cookie veya bearer token access log'a düşebilir.  
   Doğrulama: `caddy adapt` yalnız query redaction gösteriyor; request headers loglanıyor.  
   Durum: Açık.

4. **YÜKSEK — Kalite kapıları kırmızı**  
   Dosya/satır: `services/api/alembic/*`, `services/voice-agent/tests/factories.py`  
   Etki: İddia edilen production test/lint durumu doğru değil; commit öncesi kalite kapıları geçmiyor.  
   Doğrulama: Backend Ruff fail, voice-agent MyPy fail.  
   Durum: Açık.

5. **ORTA — Frontend API URL trailing slash çift slash üretiyor**  
   Dosya/satır: `apps/web/lib/api/client.ts:46-67`, `apps/web/lib/hooks/use-live-events.ts:79`  
   Etki: `API_URL` trailing slash ile build edilirse `//api/...` oluşur.  
   Durum: Açık.

6. **ORTA — Restore SQL interpolation hâlâ var**  
   Dosya/satır: `scripts/backup/postgres-restore.sh:141-156`  
   Etki: Allowlist nedeniyle pratik injection kapanmış; implementation hardening eksik.  
   Durum: Açık/orta.

## 19. Commit kapsamına alınması gereken dosyalar

RED kararı nedeniyle şu haliyle commit önerilmez. Düzeltilirse Aşama 6 production infra dosyaları commit kapsamına alınabilir: `.gitignore`, `Makefile`, `.dockerignore`, `.env.production.example`, `compose.production.yml`, `apps/web/Dockerfile`, `deploy/`, `docs/production/`, `infrastructure/docker/backup.Dockerfile`, `infrastructure/docker/voice-agent.Dockerfile`, `scripts/backup/`, `services/api/Dockerfile`, ilgili config ve test dosyaları.

## 20. Commit dışında bırakılması gereken dosyalar

Kesinlikle commit dışı: `.env.production`, `.pnpm-store/`, `.next/`, `node_modules/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage`, `tests/e2e/.auth/`, `tests/e2e/test-results/`, Caddy cert/state, Docker/backup dump artifact'ları, gerçek credential veya secret içeren her dosya.

## 21. Production açılışı öncesi operasyonel gereksinimler

- Off-site backup gerçek credential ile başarı yolunda test edilmeli; bu yapılmadan disaster recovery hazır kabul edilmemeli.
- Backup false-fail regresyonu düzeltilmeli ve tekrarlı local + remote failure + gerçek remote success matrisi yeniden koşulmalı.
- Caddy access log Cookie/Authorization redaksiyonu doğrulanmalı.
- Backend secret whitespace normalize açığı kapanmalı.
- Backend Ruff ve voice-agent MyPy geçmeli.
- Voice-agent gerçek LiveKit/OpenAI credential ile connection/lifecycle health doğrulanmalı; config-only health yeterli değil.
- Alerting/monitoring `.last-local-success` ve `.last-remote-success` ayrımını doğru yorumlamalı.

## 22. Nihai karar

**RED — Kritik/yüksek sorun açık, commit edilmemeli**

Önceki KRITIK-1 ana üretim URL problemi kapanmış görünüyor. Ancak YUKSEK-3 backend tarafında tam kapanmadı ve bu denetimde yeni yüksek riskler bulundu: backup script aralıklı false-fail, Caddy session/header log redaksiyonu eksikliği ve kalite kapılarının kırmızı olması. Off-site backup gerçek credential ile başarı yolunda hâlâ doğrulanmadığı için, bu yüksek bulgular kapansa bile production açılışı ayrıca operasyonel olarak bloke kalır.
