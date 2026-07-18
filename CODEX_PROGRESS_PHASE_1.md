# CODEX_PROGRESS_PHASE_1.md

## 1. Amaç

Denetim Planı Aşama 1 kapsamında API çalıştırılabilirliği ve migration tabanı tamamlandı:

- FastAPI uygulama giriş noktası oluşturuldu.
- Mevcut route dosyaları tek uygulamada bağlandı.
- `/health` ve `/ready` endpointleri eklendi.
- Alembic altyapısı ve ilk migration revision eklendi.
- Bootstrap owner ve seed komutları eklendi.
- API smoke, health/readiness, bootstrap, seed ve migration smoke testleri yazıldı.
- Ruff, MyPy, pytest, Alembic ve Docker Compose config doğrulamaları çalıştırıldı.

Frontend, voice-agent, OpenAI Realtime, LiveKit SIP, Netgsm ve deployment kapsam dışı bırakıldı.

## 2. Başlangıç durumu

`CODEX_AUDIT.md` bulgularına göre başlangıçta:

- `services/api/app/main.py` yoktu.
- `Makefile` `app.main:app`, `app.bootstrap`, `app.seed` ve Alembic komutlarını bekliyordu ama karşılıkları eksikti.
- Alembic klasörü, `alembic.ini` ve migration revision yoktu.
- `services/api/tests/` yoktu.
- `EmailStr` kullanımı `email-validator` bağımlılığı eksik olduğu için schema importunu kırıyordu.
- `apps/web`, `services/voice-agent`, production Docker ve docs alanları hâlâ kapsam dışı ve boş durumdaydı.

## 3. Oluşturulan dosyalar

- `services/api/app/main.py`
- `services/api/app/bootstrap.py`
- `services/api/app/seed.py`
- `services/api/alembic.ini`
- `services/api/alembic/env.py`
- `services/api/alembic/script.py.mako`
- `services/api/alembic/versions/20260717_0001_initial_schema.py`
- `services/api/tests/__init__.py`
- `services/api/tests/conftest.py`
- `services/api/tests/test_00_migration_smoke.py`
- `services/api/tests/test_app_smoke.py`
- `services/api/tests/test_health_ready.py`
- `services/api/tests/test_bootstrap.py`
- `services/api/tests/test_seed.py`
- `CODEX_PROGRESS_PHASE_1.md`

## 4. Değiştirilen dosyalar

- `.env.example`
- `Makefile`
- `services/api/app/config.py`
- `services/api/app/schemas/auth.py`
- `services/api/app/api/routes/calls.py`
- `services/api/app/api/routes/campaigns.py`
- `services/api/app/api/routes/lead_import.py`
- `services/api/app/api/routes/leads.py`
- `services/api/app/api/routes/live.py`
- `services/api/app/core/locks.py`
- `services/api/app/core/logging.py`
- `services/api/app/core/security.py`
- `services/api/app/deps.py`
- `services/api/app/models/lead.py`
- `services/api/app/models/ops.py`
- `services/api/app/services/campaign_service.py`
- `services/api/app/services/importer.py`
- `services/api/app/services/orchestrator.py`
- `services/api/app/services/prompt_builder.py`
- `services/api/app/tasks/call_tasks.py`
- `services/api/app/tasks/campaign_tasks.py`
- `services/api/app/tasks/maintenance_tasks.py`

## 5. FastAPI app wiring

`services/api/app/main.py` eklendi.

İçerik:

- `FastAPI(title="İşletme Vitrini AI Çağrı Merkezi API", version="0.1.0")`
- lifespan logging
- request ID middleware (`X-Request-ID`)
- PII-safe structured logging altyapısıyla uyumlu logging
- CORS middleware
- TrustedHost middleware
- validation, HTTP ve unhandled exception handler
- root `/health`
- root `/ready`
- mevcut router wiring

Route prefix kararı:

- API route’ları merkezi olarak `/api` altında bağlandı.
- Health/readiness root seviyede bırakıldı.

## 6. Router listesi

Bağlanan mevcut router dosyaları:

- `auth.router` → `/api/auth/*`
- `leads.router` → `/api/leads/*`
- `lead_import.router` → `/api/imports/*`
- `campaigns.router` → `/api/campaigns/*`
- `calls.router` → `/api/calls/*`
- `ops.router` → `/api/callbacks`, `/api/demo-requests`, `/api/suppression`
- `content.router` → `/api/kb`, `/api/prompts`
- `users.router` → `/api/users/*`
- `live.router` → `/api/live/events`

OpenAPI doğrulamasında 41 path üretildi.

## 7. Health/readiness

Eklenen endpointler:

- `GET /health`
- `GET /ready`

`/health` yalnız prosesin ayakta olduğunu gösterir:

```json
{"status": "ok"}
```

`/ready` şu bağımlılıkları ayrı kontrol eder:

- PostgreSQL: `select 1`
- Redis: `ping`

Başarılı cevap:

```json
{"status": "ready", "checks": {"database": "ok", "redis": "ok"}}
```

Bağımlılık hatasında 503 döner ve connection string, secret veya stack trace göstermez.

## 8. Alembic altyapısı

Eklenen dosyalar:

- `services/api/alembic.ini`
- `services/api/alembic/env.py`
- `services/api/alembic/script.py.mako`
- `services/api/alembic/versions/20260717_0001_initial_schema.py`

Alembic `DATABASE_URL` değerini `app.config.get_settings()` üzerinden alır. Bağlantı bilgisi migration dosyasına hard-code edilmedi.

`env.py`, `app.models` import ederek tüm SQLAlchemy metadata tablolarını Alembic’e görünür hale getirir.

## 9. İlk migration özeti

İlk revision:

```text
20260717_0001_initial_schema.py
```

Migration mevcut SQLAlchemy `Base.metadata` üzerinden schema oluşturup kaldırır:

- `upgrade()` → `Base.metadata.create_all(bind)`
- `downgrade()` → `Base.metadata.drop_all(bind)`

Kapsadığı tablolar:

- `users`
- `leads`
- `lead_notes`
- `lead_tags`
- `lead_tag_map`
- `import_jobs`
- `campaigns`
- `campaign_leads`
- `calls`
- `call_events`
- `call_usage`
- `call_quality_metrics`
- `suppression_list`
- `callbacks`
- `demo_requests`
- `knowledge_base_entries`
- `agent_prompt_versions`
- `provider_pricing`
- `integration_settings`
- `audit_logs`

Kontrol edilen schema unsurları:

- UUID primary key alanları
- foreign key ve cascade davranışları
- unique constraint ve indexler
- partial unique index: aktif call başına lead
- JSONB alanları
- telefon hash/ciphertext alanları
- prompt, pricing, audit ve ops tabloları

## 10. Bootstrap admin

Eklenen komut:

```bash
cd services/api
uv run python -m app.bootstrap
```

Kullanılan env değerleri:

- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_PASSWORD`

Davranış:

- İlk owner hesabını oluşturur.
- Parolayı Argon2id ile hashler.
- Düz metin parola veya hash loglamaz.
- Kullanıcı varsa duplicate üretmez.
- Var olan kullanıcıyı owner/active hale getirir.
- Eksik env değerlerinde hata verir.
- Production’da kısa veya varsayılan zayıf parola kabul etmez.

Doğrulama:

- İlk çalıştırma: `owner created: owner@example.test`
- İkinci çalıştırma: `owner exists: owner@example.test`

## 11. Seed verileri

Eklenen komut:

```bash
cd services/api
uv run python -m app.seed
```

Seed içerikleri:

- OpenAI provider pricing:
  - `gpt-realtime-2.1-mini`
  - `gpt-realtime-2.1`
- Güvenli integration settings:
  - default model
  - default voice
  - Netgsm dakika fiyat placeholder değeri
  - USD/TRY kur placeholder kaydı
- Knowledge base:
  - paket bilgileri
  - hizmet açıklaması
  - görüşme hedefi
- İlk active agent prompt version:
  - `default-v1`

Doğrulama:

- İlk çalıştırma: `kb=5, pricing=2, prompts=1, settings=4`
- İkinci çalıştırma: `kb=0, pricing=0, prompts=0, settings=0`

## 12. Testler

Eklenen testler:

- App smoke:
  - `app.main:app` import ediliyor.
  - FastAPI app oluşuyor.
  - OpenAPI schema üretiliyor.
  - Temel router path’leri schema’da görünüyor.
- Health:
  - `/health` 200 dönüyor.
  - Secret/connection string sızdırmıyor.
- Readiness:
  - DB/Redis ok olduğunda 200.
  - DB veya Redis hata verdiğinde 503.
  - Connection string sızdırmıyor.
- Bootstrap:
  - owner oluşturuyor.
  - ikinci çalıştırmada duplicate oluşturmuyor.
  - parola düz metin tutulmuyor.
  - eksik env değerinde hata veriyor.
- Seed:
  - kayıtları oluşturuyor.
  - ikinci çalıştırmada duplicate üretmiyor.
  - pricing kayıtları doğru model isimlerine bağlı.
- Migration smoke:
  - `downgrade base`
  - `upgrade head`
  - temel tabloların varlığı
  - tekrar downgrade/upgrade round-trip

Pytest sonucu:

```text
8 passed, 1 warning in 3.01s
```

Uyarı:

- FastAPI/Starlette `TestClient` tarafında `httpx` deprecation uyarısı. Test başarısını etkilemedi.

## 13. Lint ve typecheck sonuçları

Ruff:

```text
uv run ruff check app tests
All checks passed!
```

MyPy:

```text
uv run mypy app
Success: no issues found in 71 source files
```

Not:

- İlk `uv run` denemesi sandbox içinde `~/.cache/uv` erişimi nedeniyle başarısız oldu.
- Aynı komutlar izinli çalıştırıldığında başarıyla tamamlandı.

## 14. Migration doğrulama sonuçları

Çalıştırılan komutlar:

```bash
cd services/api
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

Sonuç:

- `upgrade head` başarılı.
- `downgrade base` başarılı.
- tekrar `upgrade head` başarılı.

Ek olarak pytest migration smoke testi `ivac_test` veritabanında round-trip doğruladı.

## 15. Docker config sonucu

Çalıştırılan komut:

```bash
docker compose -f docker-compose.dev.yml config
```

Sonuç:

- Compose config başarılı render edildi.
- Default servisler: Postgres + Redis.
- LiveKit profile bu aşamada çalıştırılmadı.

Development servisleri:

```bash
docker compose -f docker-compose.dev.yml up -d postgres redis
```

çıktısında iki container zaten `Running` durumundaydı. Bu nedenle test sonunda `down` çalıştırılmadı; önceden ayakta olan development servisleri kapatılmadı.

## 16. Düzeltilen mevcut kod hataları

- `EmailStr` import hatası:
  - `email-validator` bağımlılığı kurulu değildi.
  - Paket eklemek yerine `services/api/app/schemas/auth.py` içinde dependency’siz basit e-posta validasyonu kullanıldı.
- Ruff/MyPy temizliği:
  - uzun satırlar bölündü.
  - bazı import sıraları ve unused importlar temizlendi.
  - `apply_async(args=[...])` tuple formatına çevrildi.
  - bazı helper fonksiyonlara tip anotasyonları eklendi.
  - Redis session member decoding type-safe hale getirildi.
  - `locks.py` release cleanup için `contextlib.suppress` kullanıldı.
- `Makefile`:
  - `db-downgrade` eklendi.
  - API lint/typecheck/test hedefleri gerçek mevcut API kapsamına göre düzeltildi.
  - Henüz olmayan `agent` ve `web` hedefleri korunup açık hata mesajı verir hale getirildi.
  - `check` hedefi Aşama 1 API kalite kapılarına indirildi.

## 17. Başarısız veya doğrulanamayan noktalar

- İlk `uv run` komutları sandbox içinde `~/.cache/uv` erişim hatası verdi; izinli tekrar çalıştırıldı ve geçti.
- Production Docker doğrulanmadı; bu aşamada `docker-compose.prod.yml` hâlâ yok ve kapsam dışı.
- LiveKit/SIP profile çalıştırılmadı; kapsam dışı.
- OpenAI, LiveKit ve Netgsm dış servislerine hiçbir çağrı yapılmadı.
- Frontend ve voice-agent oluşturulmadı.

## 18. Bilinen eksikler

Aşama 1 sonrası hâlâ eksik olanlar:

- Next.js yönetim paneli.
- Voice-agent servisi.
- OpenAI Realtime runtime.
- LiveKit SIP participant oluşturma akışı.
- Netgsm trunk adapter ve canlı doğrulama.
- Production Docker Compose, Dockerfile ve Caddy config.
- Gerçek integration test kapsamı: API endpoint auth flows, campaign tick, call orchestrator fake provider, import endpoint multipart akışı.
- API route’ları için ayrıntılı authorization testleri.
- Explicit Alembic operation migration yerine metadata-driven ilk migration kullanıldı; ileride schema değişikliklerinde operasyon bazlı revision üretilmesi önerilir.

## 19. Sonraki önerilen aşama

Sıradaki önerilen aşama: Backend test iskeleti ve kritik unit/integration testleri genişletmek.

Öncelik:

1. Auth login/logout/me integration testleri.
2. Lead import endpoint multipart testleri.
3. Call policy ve campaign tick edge-case testleri.
4. Fake telephony provider ile orchestrator testleri.
5. Internal voice-agent API contract tasarımı.

Voice-agent/OpenAI/LiveKit tarafına geçmeden önce API contract ve DB davranışı daha fazla testle sabitlenmeli.

## 20. Git durumu

Repo hâlâ ilk commit öncesi gibi görünüyor; `git status --short` tüm proje dosyalarını untracked gösteriyor.

Commit veya push yapılmadı.

Son doğrulamada görünen üst seviye durum:

```text
?? .env.example
?? .gitignore
?? .prettierrc
?? AGENTS.md
?? CHANGELOG.md
?? CLAUDE.md
?? CODEX_AUDIT.md
?? CODEX_PROGRESS_PHASE_1.md
?? DECISIONS.md
?? IMPLEMENTATION_PLAN.md
?? Makefile
?? PROJECT_STATUS.md
?? PROMPTS.md
?? TODO.md
?? docker-compose.dev.yml
?? infrastructure/
?? package.json
?? pnpm-workspace.yaml
?? services/
?? turbo.json
```
