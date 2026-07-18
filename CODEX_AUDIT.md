# CODEX_AUDIT.md

## 1. Yönetici özeti

Bu denetim salt-okunur teknik ikinci göz olarak yapıldı. Proje, hedef mimarinin yalnızca API/domain katmanına doğru ilerlemiş durumda. FastAPI servisinde model, schema, route, servis ve Celery görev dosyaları önemli ölçüde yazılmış; lead import, kampanya, arama politikası, RBAC, audit, PII şifreleme, maliyet hesaplama ve LiveKit dispatch adapter iskeleti var.

Ancak proje üretime hazır değildir. En kritik boşluklar:

- FastAPI uygulama giriş noktası yok: `Makefile:39` `app.main:app` bekliyor, fakat `services/api/app/main.py` bulunmuyor.
- Alembic altyapısı yok: `services/api/pyproject.toml:12` Alembic bağımlılığı var, `Makefile:26-30` migration komutları var, fakat `alembic.ini`, `alembic/`, revision dosyaları yok.
- Frontend, voice-agent, production Docker, LiveKit/SIP config ve test dosyaları yok: ilgili klasörler var ama dosya içermiyor.
- OpenAI Realtime gerçek konuşma motoru uygulanmamış; yalnız model kataloğu ve seçim doğrulaması var (`services/api/app/providers/conversation.py:42-92`).
- LiveKit SIP telefon bacağını oluşturacak voice-agent uygulanmamış; API tarafı yalnız agent dispatch oluşturuyor (`services/api/app/providers/telephony.py:55-73`).

Kaba tamamlanma aralığı: üretim hedefinin yaklaşık %25-35'i. API domain iskeleti iyi bir başlangıç; ancak çalışır ürün olmaktan çok uzak.

## 2. İncelenen proje ve Git durumu

Çalışma klasörü:

```text
/Users/kadirugur/Projects/isletme-vitrini-ai-cagri
```

Git durumu:

- Git repo var: `git rev-parse --show-toplevel` aynı klasörü döndürdü.
- `git log --oneline -5` çıktı vermedi; commit geçmişi yok veya mevcut branch'te commit yok.
- `git status --short` tüm proje dosyalarını untracked gösteriyor.
- `git diff --stat` ve `git diff --name-only` boş; çünkü dosyalar izlenmiyor.

Önemli mevcut dosyalar:

- `IMPLEMENTATION_PLAN.md`
- `package.json`, `pnpm-workspace.yaml`, `turbo.json`
- `docker-compose.dev.yml`, `Makefile`, `.env.example`
- `services/api/pyproject.toml`
- `services/api/app/**`

Boş veya dosyasız görünen hedef alanlar:

- `apps/web`
- `packages/config`, `packages/shared-types`, `packages/ui`
- `services/voice-agent`
- `services/worker`
- `docs`
- `tests`, `tests/e2e`, `tests/fixtures`
- `infrastructure/caddy`, `infrastructure/docker`, `infrastructure/livekit`

## 3. Claude Code’un kaldığı tahmini aşama

Çıkarım: Claude Code en son API backend domain katmanı üzerinde çalışıyordu. Kanıt:

- `IMPLEMENTATION_PLAN.md:38` uygulama sırasını A1-A9 olarak listeliyor.
- `services/api/app` altında 68 Python dosyası var.
- `apps/web`, `services/voice-agent`, `tests`, `docs` ve production altyapı klasörleri dosyasız.
- `Makefile:39`, `Makefile:47`, `Makefile:78` henüz var olmayan `app.main`, `agent.main`, `docker-compose.prod.yml` hedeflerine referans veriyor.

En son güvenilir tamamlanan aşama: API domain/model/service scaffold ve bazı iş kuralları.

Yarım kalan ilk kritik özellik: çalıştırılabilir FastAPI uygulaması + Alembic migration tabanı. Bunlar olmadan mevcut modeller ve endpointler doğrulanabilir bir uygulamaya dönüşmüyor.

Devam çalışması şu sırayla başlamalı:

1. API entrypoint, router wiring, health endpoint ve bootstrap/seed durumunu netleştirmek.
2. Alembic migration altyapısını modellerle uyumlu kurmak.
3. API smoke/integration testlerini eklemek.

## 4. Tamamlanmış ve kanıtlanmış bölümler

Bu başlıkta "tamamlanmış" ifadesi yalnız statik kod düzeyinde kanıtlanmış alt parçalar içindir; uçtan uca ürün tamamlandı anlamına gelmez.

- Monorepo kök manifestleri: `package.json:1-18`, `pnpm-workspace.yaml:1-4`, `turbo.json:1-13`.
- API bağımlılık ve kalite konfigürasyonu: `services/api/pyproject.toml:1-67`.
- PII şifreleme ve telefon hash yardımcıları: AES-GCM + HMAC tasarımı `services/api/app/core/crypto.py:25-53`.
- RBAC izin matrisi: roller ve permission setleri `services/api/app/core/rbac.py:8-70`.
- Session/CSRF temel yardımcıları: opaque Redis session, Argon2, CSRF HMAC `services/api/app/core/security.py:34-137`.
- Audit log yazma helper'ı: `services/api/app/core/audit.py:11-38`.
- Call state enum ve geçiş tablosu: `services/api/app/models/enums.py:58-131`.
- Lead import parserları: XLSX/CSV/JSON parse kodu `services/api/app/services/importer.py:87-160`.
- Development compose config parse ediliyor: `docker compose -f docker-compose.dev.yml config` başarılı; yalnız Postgres/Redis default servisi render edildi.
- Python kaynakları parse edilebildi: `services/api/.venv/bin/python -m compileall -q services/api/app` hata vermedi.

## 5. Kısmen tamamlanan bölümler

- Backend temel yapısı: çok sayıda route/service/model var, fakat FastAPI app entrypoint yok. Route dosyaları örn. `services/api/app/api/routes/auth.py`, `leads.py`, `campaigns.py`, `calls.py`; buna rağmen `services/api/app/main.py` yok.
- Authentication: login/logout/me endpointleri var (`services/api/app/api/routes/auth.py:61-123`), session/CSRF helperları var; ancak bootstrap admin ve uygulama wiring yok.
- Lead yönetimi: listeleme, güncelleme, telefon reveal, not/tag/export var (`services/api/app/api/routes/leads.py:42-175`, `178-242`, `245-260+`); frontend ve test yok.
- Kampanya yönetimi: CRUD benzeri endpointler, status geçişleri ve lead ekleme var (`services/api/app/api/routes/campaigns.py:44-225`); gerçek tick/queue entegrasyonu kısmen var.
- Arama kuyruğu: `initiate_call` Call kaydı oluşturup Celery görevi kuyruğa atıyor (`services/api/app/services/orchestrator.py:51-133`); ancak gerçek worker/runtime doğrulanmamış.
- Retry sistemi: hesaplama fonksiyonu ve campaign terminal handling var (`services/api/app/services/call_policy.py:148-175`, `services/api/app/services/campaign_service.py:124-145`); test yok.
- Günlük ve eşzamanlı arama limiti: policy fonksiyonları var (`services/api/app/services/call_policy.py:55-109`), DB sorgusuna dayanıyor; migration/test yok.
- Distributed lock: Redis SET NX lock var (`services/api/app/core/locks.py:16-39`), orchestrator kullanıyor (`services/api/app/services/orchestrator.py:82-124`).
- Suppression listesi: model ve endpointler var (`services/api/app/models/ops.py:16-31`, `services/api/app/api/routes/ops.py:153-233`); agent tool bağlantısı yok.
- Callback ve demo talebi: modeller ve liste/güncelleme endpointleri var (`services/api/app/models/ops.py:34-72`, `services/api/app/api/routes/ops.py:38-147`); agent tool üretimi yok.
- Provider interface'leri: protocol/dataclass seviyesinde mevcut (`services/api/app/providers/base.py:19-92`).
- Usage ve maliyet hesaplama: pricing model ve compute fonksiyonları var (`services/api/app/models/pricing.py:12-48`, `services/api/app/services/cost_service.py:54-99`); provider usage ingestion yok.
- Prompt versiyonlama ve bilgi bankası: modeller ve CRUD endpointleri var (`services/api/app/models/content.py:15-42`, `services/api/app/api/routes/content.py:28-134`); seed yok.
- SSE canlı olay akışı: endpoint var (`services/api/app/api/routes/live.py:25-54`), event bus ile bağlantı var; frontend yok.

## 6. Scaffold veya placeholder bölümler

- Frontend: `apps/web` klasörü var, dosya yok. Next.js config, `package.json`, sayfalar, komponentler yok.
- Shared packages: `packages/config`, `packages/shared-types`, `packages/ui` klasörleri var, dosya yok.
- Voice agent: `services/voice-agent` klasörü var, dosya yok. `Makefile:47-48` `agent.main` bekliyor.
- Worker servis klasörü: `services/worker` klasörü var, dosya yok. Celery worker kodu API paketinde var (`services/api/app/worker.py:17-52`), ama ayrı Docker/entrypoint yok.
- Docs: `docs` klasörü var, istenen doküman dosyaları yok.
- E2E/tests: `tests`, `tests/e2e`, `tests/fixtures` klasörleri var, dosya yok.
- ImportedLeadProvider sembolik: `services/api/app/providers/places.py:88-98` arama ve detay için boş sonuç dönüyor; asıl iş importer'da.
- OpenAI Realtime provider: API tarafında yalnız katalog doğrulaması var (`services/api/app/providers/conversation.py:42-92`), gerçek engine yok.

## 7. Başlanmamış bölümler

- Next.js yönetim paneli.
- OpenAI Realtime LiveKit Agents runtime.
- Agent tool fonksiyonları: `finalize_call_outcome`, `schedule_callback`, `request_demo_link`, suppression tool vb. bulunamadı.
- LiveKit `CreateSIPParticipantRequest` ile gerçek SIP participant oluşturma; plan dokümanında var (`IMPLEMENTATION_PLAN.md:10`) ama kodda yok.
- Netgsm outbound trunk oluşturma/yönetme adapteri; env alanları var (`.env.example:30-37`), runtime kod yok.
- Production Docker compose: `Makefile:78` referans veriyor, `docker-compose.prod.yml` yok.
- Dockerfile dosyaları yok.
- Caddy config yok.
- LiveKit server/SIP config dosyaları yok; `docker-compose.dev.yml:52` ve `64` dosyalara referans veriyor ama `infrastructure/livekit` altında dosya yok.
- Alembic migrationları ve `alembic.ini`.
- API main entrypoint.
- README, setup, architecture ve deployment dokümanları.
- Unit/integration/E2E testler.

## 8. Şüpheli veya hatalı uygulamalar

- `Makefile:39` `uvicorn app.main:app` çalıştırıyor; `services/api/app/main.py` yok. API şu haliyle Makefile üzerinden başlamaz.
- `Makefile:47-48` `services/voice-agent` altında `agent.main` bekliyor; klasörde dosya yok.
- `Makefile:78` `docker-compose.prod.yml` bekliyor; dosya yok.
- `docker-compose.dev.yml:52` ve `docker-compose.dev.yml:64` LiveKit config dosyalarına mount yapıyor; `infrastructure/livekit` dosyasız.
- `services/api/pyproject.toml:64-67` pytest `tests` dizinini bekliyor; `services/api/tests` yok, kök `tests` de boş.
- `services/api/app/core/locks.py:36-39` lock release hatalarını yutuyor. Bu savunulabilir olabilir, ama lock sızıntısı veya Redis komut hatası görünmez kalır.
- `services/api/app/tasks/call_tasks.py:123-128` ve `153-157` geniş `except Exception` ile state machine hatasında doğrudan status yazıyor. Operasyonel olarak pragmatik, ancak test ve audit olmadan hatalı state geçişlerini saklayabilir.
- `services/api/app/api/routes/live.py:45-53` SSE cleanup hatalarını yutuyor; düşük risk ama gözlemlenebilirlik zayıf.
- `services/api/app/services/campaign_tasks.py:70-71` kampanya tick'te `actor_role="owner"` ve `allow_test_engine=True` kullanıyor. Kampanya oluşturulurken doğrulama yapıldığı varsayılıyor; DB elle değişirse premium/test engine kapısı aşılabilir.
- `services/api/app/services/orchestrator.py:73-80` telefonu çözüyor ama `phone_e164` yalnız policy için kullanılıyor; sonra `build_dial_info` içinde tekrar çözülecek. PII bellek süresi kısa tutulmuş, ama gerçek dial paketi internal endpoint olmadan tamamlanmamış.
- `.env.example:9-12` ve `docker-compose.dev.yml:10-12` development DB bilgilerini hard-code ediyor. Secret değil ama production'a taşınmaması gerekir.
- `services/api/app/services/settings_service.py` incelendiğinde entegrasyonların "configured" durumunu env var varlığına göre gösterecek yapı var; gerçek bağlantı testi yapmıyor.

## 9. OpenAI Realtime entegrasyonu durumu

Durum: Yalnızca scaffold veya placeholder.

Kanıt:

- Env alanları var: `.env.example:39-44`.
- Model katalog doğrulaması var: `services/api/app/providers/conversation.py:42-92`.
- Campaign ve Call modellerinde `openai_realtime`, model ve voice alanları var: `services/api/app/models/campaign.py:22-31`, `services/api/app/models/call.py:55-60`.
- Gerçek `livekit.plugins.openai`, `openai.realtime.RealtimeModel`, `AgentSession`, turn detection veya tool registration kodu bulunamadı.
- `services/voice-agent` dosyasız.

Sonuç: Realtime entegrasyonu üretim kodu olarak başlamamış; API sadece seçilecek model bilgisini saklamaya hazırlanmış.

## 10. LiveKit ve Netgsm entegrasyonu durumu

Durum: Kısmen uygulanmış.

Kanıt:

- Development compose LiveKit ve SIP profili tanımlıyor (`docker-compose.dev.yml:47-71`), fakat config dosyaları yok.
- API telephony provider LiveKit Agent Dispatch oluşturuyor (`services/api/app/providers/telephony.py:55-73`).
- Telefon numarası dispatch metadata'ya yazılmıyor, yalnız `call_id` taşınıyor (`services/api/app/providers/telephony.py:61-66`).
- Hangup ve transfer için LiveKit API çağrıları var (`services/api/app/providers/telephony.py:75-99`).
- SIP participant oluşturma API tarafında yok; yorumlar bunu voice-agent'a bırakıyor (`services/api/app/providers/telephony.py:3-8`), fakat voice-agent yok.
- Netgsm için yalnız env alanları var (`.env.example:30-37`); trunk oluşturma, doğrulama veya Netgsm özel adapter kodu yok.

Sonuç: API dispatch tarafı yazılmaya başlanmış; gerçek outbound SIP çağrı zincirinin kritik yarısı eksik.

## 11. Frontend durumu

Durum: Başlanmamış.

Kanıt:

- `apps/web` klasörü dosyasız.
- Next.js `package.json`, `next.config`, `tsconfig`, `app/` veya `pages/` yok.
- Yönetim paneli sayfaları, canlı izleme ekranı, kampanya/lead/import UI yok.
- Kök workspace `apps/*` kapsamını tanımlıyor (`pnpm-workspace.yaml:1-4`), fakat gerçek app manifesti yok.

## 12. Backend ve veritabanı durumu

Durum: Backend kısmen uygulanmış; veritabanı modeli var ama migration ve çalıştırılabilir app eksik.

Kanıt:

- SQLAlchemy modelleri kapsamlı: leads (`services/api/app/models/lead.py`), campaigns (`campaign.py`), calls (`call.py`), ops (`ops.py`), content (`content.py`), pricing (`pricing.py`), system (`system.py`), user (`user.py`).
- DB session helper var: `services/api/app/db/session.py:14-35`.
- Alembic bağımlılığı var (`services/api/pyproject.toml:12`) ama `alembic.ini` ve migration klasörü yok.
- API main entrypoint yok.
- Route dosyaları var ama router include eden uygulama yok.

Özellik matrisi:

| Özellik | Durum | Kanıt |
|---|---|---|
| 1. Monorepo ve workspace | Kısmen uygulanmış | `package.json:1-18`, `pnpm-workspace.yaml:1-4`; workspace paketleri yok |
| 2. Frontend temel yapısı | Başlanmamış | `apps/web` dosyasız |
| 3. Backend temel yapısı | Kısmen uygulanmış | `services/api/app/api/routes/*.py`, ama `app/main.py` yok |
| 4. Veritabanı modelleri | Büyük ölçüde tamamlanmış | `services/api/app/models/*.py` |
| 5. Alembic migrationları | Başlanmamış | Alembic bağımlılığı var, config/revision yok |
| 6. Authentication | Kısmen uygulanmış | `auth.py:61-123`, `security.py:34-137` |
| 7. RBAC | Büyük ölçüde tamamlanmış | `rbac.py:8-70`, route dependency kullanımı |
| 8. Audit log | Kısmen uygulanmış | `audit.py:11-38`, model `system.py:33-47` |
| 9. Telefon şifreleme ve hashleme | Büyük ölçüde tamamlanmış | `crypto.py:25-53`, lead model PII alanları |
| 10. Lead yönetimi | Kısmen uygulanmış | `leads.py:42-242` |
| 11. XLSX, CSV ve JSON import | Büyük ölçüde tamamlanmış | `importer.py:87-160`, `lead_import.py:48-121` |
| 12. Duplicate lead kontrolü | Kısmen uygulanmış | phone_hash/place_id kontrolü `importer.py:208-261`; DB unique yalnız place_id |
| 13. Kampanya yönetimi | Kısmen uygulanmış | `campaigns.py:44-260+`, `campaign_service.py` |
| 14. Arama kuyruğu | Kısmen uygulanmış | `orchestrator.py:129-133`, `call_tasks.py:33-83` |
| 15. Retry sistemi | Kısmen uygulanmış | `call_policy.py:148-175`, `campaign_service.py:124-145` |
| 16. Günlük arama limiti | Kısmen uygulanmış | `call_policy.py:55-64`, `93-109` |
| 17. Eşzamanlı arama limiti | Kısmen uygulanmış | `call_policy.py:67-73`, `97-109` |
| 18. Distributed lock | Kısmen uygulanmış | `locks.py:16-39`, `orchestrator.py:82-124` |
| 19. Suppression listesi | Kısmen uygulanmış | `ops.py:16-31`, route `ops.py:153-233` |
| 20. Callback sistemi | Kısmen uygulanmış | model `ops.py:34-54`, route `ops.py:38-76` |
| 21. Demo talebi sistemi | Kısmen uygulanmış | model `ops.py:56-72`, route `ops.py:82-147` |
| 22. Provider interface’leri | Büyük ölçüde tamamlanmış | `providers/base.py:19-92` |
| 23. OpenAI Realtime provider | Başlanmamış | gerçek provider yok, yalnız katalog `conversation.py` |
| 24. LiveKit voice agent | Başlanmamış | `services/voice-agent` dosyasız |
| 25. Agent tool fonksiyonları | Başlanmamış | tool route/function bulunamadı |
| 26. LiveKit SIP bağlantısı | Kısmen uygulanmış | dispatch var, SIP participant yok |
| 27. Netgsm telephony adapter | Yalnızca scaffold veya placeholder | env var var, adapter yok |
| 28. Outbound call orchestrator | Kısmen uygulanmış | `orchestrator.py:51-162` |
| 29. Call state machine | Büyük ölçüde tamamlanmış | `enums.py:95-131`, `call_service.py:64-98` |
| 30. Usage ve maliyet hesaplama | Kısmen uygulanmış | `cost_service.py:54-99`; usage ingestion yok |
| 31. Prompt versiyonlama | Kısmen uygulanmış | `content.py:28-42`, `prompt_builder.py:32-104` |
| 32. Bilgi bankası | Kısmen uygulanmış | `content.py:15-26`, route `content.py:28-79` |
| 33. Yönetim paneli sayfaları | Başlanmamış | frontend dosyası yok |
| 34. Canlı arama izleme | Kısmen uygulanmış | `calls.py:118-129`, SSE `live.py:25-54`; UI yok |
| 35. WebSocket veya SSE | Kısmen uygulanmış | SSE route var `live.py:25-54` |
| 36. Unit testler | Başlanmamış | test dosyası yok |
| 37. Integration testler | Başlanmamış | test dosyası yok; `init-test-db.sql` var |
| 38. E2E testler | Başlanmamış | `tests/e2e` dosyasız |
| 39. Docker development yapısı | Kısmen uygulanmış | `docker-compose.dev.yml` config parse başarılı; LiveKit mount dosyaları eksik |
| 40. Docker production yapısı | Başlanmamış | `docker-compose.prod.yml` yok |
| 41. Güvenlik kontrolleri | Kısmen uygulanmış | CSRF/RBAC/PII/log redaction var; test ve app wiring yok |
| 42. Dokümantasyon | Kısmen uygulanmış | `IMPLEMENTATION_PLAN.md` var; istenen docs dosyaları yok |

## 13. Test ve build altyapısı durumu

- Kök scriptler var (`package.json:5-12`), fakat workspace app/package manifestleri yok.
- Python kalite araçları pyproject'te tanımlı (`services/api/pyproject.toml:44-67`).
- Test dizinleri dosyasız.
- `services/api/.venv/bin/python -m compileall -q services/api/app` başarılı oldu; bu yalnız syntax/parse kontrolüdür.
- Full lint/typecheck/test/build çalıştırılmadı; proje eksik manifest ve entrypointler nedeniyle pahalı ve yanıltıcı olurdu.

## 14. Docker ve production hazırlığı

- Development compose default Postgres+Redis için geçerli config üretiyor (`docker-compose.dev.yml:6-45`).
- LiveKit/SIP profile tanımı var (`docker-compose.dev.yml:47-71`) ama mount edilen config dosyaları yok.
- Production compose yok.
- Dockerfile yok.
- Caddy config yok.
- Worker ve voice-agent image/entrypoint yok.

## 15. Güvenlik bulguları

Olumlu:

- `.env` ve secret dosyaları gitignore'da (`.gitignore:1-8`).
- PII telefon düz metin tutulmuyor; ciphertext/hash/last4 alanları var (`services/api/app/models/lead.py:51-55`).
- Phone reveal audit'leniyor (`services/api/app/api/routes/leads.py:156-175`).
- CSRF mutasyon isteklerinde zorunlu (`services/api/app/deps.py:52-56`).
- Development'ta canlı aramalar default kapalı (`.env.example:55-61`, `services/api/app/services/call_policy.py:76-90`).

Riskler:

- Entry point ve middleware olmadığı için CORS/security headers/app-level exception policy doğrulanamıyor.
- Migration yok; DB constraint'leri gerçekten uygulanmıyor.
- Bazı geniş `except Exception` blokları operasyonel sorunları saklayabilir.
- API route'larının tamamında PII-safe logging varsayımı var; gerçek logging middleware yokluğu nedeniyle uçtan uca doğrulanmadı.
- `docker-compose.dev.yml` development DB credentialları içeriyor; production ayrımı olmayan kopyalama riski var.

## 16. Claude raporlarıyla kod arasındaki tutarsızlıklar

`IMPLEMENTATION_PLAN.md` plan niteliğinde güvenilir; tamamlandı raporu değil. Kodla karşılaştırıldığında şu iddialar henüz gerçekleşmemiş:

- Plan `docs/netgsm-sip-setup.md` ve `docs/live-call-checklist.md` bekliyor (`IMPLEMENTATION_PLAN.md:30-31`), `docs` klasörü boş.
- Plan voice-agent tarafında OpenAI Realtime runtime öngörüyor (`IMPLEMENTATION_PLAN.md:12`, `21`), `services/voice-agent` boş.
- Plan production Docker Compose hedefliyor, fakat yalnız dev compose var.
- Plan A5/A6/A7/A8/A9 aşamalarını listeliyor (`IMPLEMENTATION_PLAN.md:38`); kod durumu A3/A4 ile A6 API dispatch arasına sıkışmış görünüyor.

## 17. Devam edilmesi gereken ilk görev

İlk görev: API'yi çalıştırılabilir ve migration ile doğrulanabilir hale getirmek.

Kapsam:

- `services/api/app/main.py` oluşturulmalı.
- Mevcut router'lar tek FastAPI app'e include edilmeli.
- Health/readiness endpointleri eklenmeli.
- Alembic config ve ilk migration üretilmeli.
- Bootstrap/seed eksikleri netleştirilmeli; `Makefile:32-36` şu an var olmayan `app.seed` ve `app.bootstrap` modüllerine referans veriyor.
- Minimal API smoke testleri eklenmeli.

Bu yapılmadan frontend veya voice-agent geliştirmek yüksek riskli olur; çünkü API contract ve DB şeması doğrulanmamış.

## 18. Token-verimli kalan çalışma planı

1. API çalıştırılabilirlik ve migration tabanı
   - Amaç: Backend'i import edilebilir, başlatılabilir, migration uygulanabilir yapmak.
   - Dosyalar: `services/api/app/main.py`, `services/api/app/api/routes/*`, `services/api/app/db/*`, Alembic dosyaları.
   - Bağımlılık: Yok.
   - Tamamlanma kriteri: `uvicorn app.main:app` import eder; `alembic upgrade head` boş DB'de çalışır.
   - Test: API import smoke, Alembic upgrade/downgrade smoke.
   - Önerilen model: Codex.

2. Backend test iskeleti ve kritik unit testler
   - Amaç: Policy, crypto, importer, state machine ve RBAC için hızlı testler.
   - Dosyalar: `services/api/tests/**`, `services/api/pyproject.toml`.
   - Bağımlılık: Aşama 1.
   - Tamamlanma kriteri: `uv run pytest -q` servis başlatmadan geçer.
   - Test: Pytest.
   - Önerilen model: Codex.

3. Internal voice-agent API contract
   - Amaç: Agent'ın dial info alması ve tool sonuçlarını API'ye yazması için endpointleri tamamlamak.
   - Dosyalar: `services/api/app/api/routes/internal*.py`, `call_service.py`, `ops.py`, schemas.
   - Bağımlılık: Aşama 1-2.
   - Tamamlanma kriteri: Bearer token ile internal endpoint testleri geçer; PII audit kuralları korunur.
   - Test: API integration tests.
   - Önerilen model: Codex.

4. LiveKit voice-agent minimal gerçek runtime
   - Amaç: LiveKit Agents + OpenAI Realtime session + SIP participant akışını kodlamak.
   - Dosyalar: `services/voice-agent/**`, `services/api/providers/telephony.py`, docs.
   - Bağımlılık: Aşama 3.
   - Tamamlanma kriteri: Test provider ile agent job boot eder; gerçek API çağrısı env kapalıyken yapılmaz.
   - Test: Mocked/unit tests; gerçek LiveKit checklist ayrı.
   - Önerilen model: Claude Sonnet; SDK yüzeyi karmaşıklaşırsa Claude Opus/Fable.

5. Campaign worker integration hardening
   - Amaç: Campaign tick, retry, terminal outcome ve callback/demo effects testlerini kapatmak.
   - Dosyalar: `campaign_tasks.py`, `campaign_service.py`, `call_tasks.py`, tests.
   - Bağımlılık: Aşama 1-3.
   - Tamamlanma kriteri: Queue seçimleri ve retry edge-case'leri testli.
   - Test: Pytest + fake Redis/DB integration.
   - Önerilen model: Codex.

6. Frontend yönetim paneli MVP
   - Amaç: Lead import/list, campaign list/control, live calls, callbacks/demo requests ekranları.
   - Dosyalar: `apps/web/**`, `packages/ui/**`, `packages/shared-types/**`.
   - Bağımlılık: Aşama 1 ve API schema stabilizasyonu.
   - Tamamlanma kriteri: Login sonrası temel akışlar çalışır, SSE görünür.
   - Test: Typecheck + Playwright smoke.
   - Önerilen model: Claude Sonnet.

7. Docker production ve ops dokümantasyonu
   - Amaç: Production compose, Dockerfile, Caddy, LiveKit/SIP config, checklist.
   - Dosyalar: `docker-compose.prod.yml`, `infrastructure/**`, `docs/**`.
   - Bağımlılık: Aşama 4-6.
   - Tamamlanma kriteri: `docker compose -f docker-compose.prod.yml config` geçer; docs env ve runbook içerir.
   - Test: Compose config validation.
   - Önerilen model: Codex.

8. Uçtan uca güvenli staging doğrulaması
   - Amaç: Gerçek servisleri kontrollü allowlist ile doğrulamak.
   - Dosyalar: test checklist, smoke scripts, docs.
   - Bağımlılık: Aşama 7.
   - Tamamlanma kriteri: Tek allowlist numarasıyla LiveKit/OpenAI/Netgsm akışı manuel onaylı tamamlanır.
   - Test: `docs/live-call-checklist.md` üzerinden manuel staging run.
   - Önerilen model: Claude Sonnet; canlı entegrasyon sırasında kullanıcı onayı şart.

## 19. Çalıştırılan komutlar ve sonuçları

- `pwd` → `/Users/kadirugur/Projects/isletme-vitrini-ai-cagri`
- `git rev-parse --show-toplevel 2>/dev/null || true` → aynı klasör.
- `git status --short` → proje dosyalarının tamamı untracked.
- `git diff --stat` → boş.
- `git diff --name-only` → boş.
- `git log --oneline -5 2>/dev/null || true` → boş.
- `find` komutlarıyla kök, `apps`, `services`, `packages`, `infrastructure`, `docs`, `tests` envanteri alındı.
- `nl -ba` ile manifest, config, route, model, service, provider ve task dosyaları okundu.
- `rg -n "TODO|FIXME|NotImplemented|pass..."` → production kritik TODO/FIXME yoğunluğu yok; bazı boş exception sınıfları, best-effort `except Exception` ve placeholder provider bulundu.
- `rg -n "openai|Realtime|LiveKit|SIP|Netgsm..."` → OpenAI runtime yok, LiveKit dispatch var, SIP participant/voice-agent yok.
- `services/api/.venv/bin/python -m compileall -q services/api/app` → syntax/parse kontrolü başarılı.
- `docker compose -f docker-compose.dev.yml config` → default Postgres/Redis compose config başarılı render edildi; LiveKit profile config dosya varlığı bu komutla doğrulanmadı.
- `find services/api/app -type f -name '*.py' | wc -l` → 68 Python dosyası.

Not: `.env` veya secret dosyaları açılmadı. Paket yükleme, servis başlatma, migration, DB yazma, API/LiveKit/Netgsm/OpenAI çağrısı yapılmadı.

## 20. Değiştirilen dosyalar

```text
CODEX_AUDIT.md
```
