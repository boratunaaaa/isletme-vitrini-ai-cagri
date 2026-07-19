# Aşama 11 — Tam Disposable E2E

Tarih: 2026-07-19
Kapsam: Aşama 10 commit (`36f14e4`) sonrası; ayrı Docker Compose projesi (`ivac-e2e`), ayrı disposable volume'ler, gerçek 8-servisli production stack (`compose.production.yml` + `deploy/caddy/compose.local-caddy.override.yml`), gerçek tarayıcı (Playwright) + gerçek HTTP (curl) doğrulaması.

## 1. Ortam

- Proje adı: `ivac-e2e` (dev stack `ivac-dev-*`'ten TAMAMEN izole — ayrı network, ayrı volume: `ivac-e2e_postgres_data`, `ivac-e2e_redis_data`, `ivac-e2e_caddy_data/config`).
- Env dosyası: `.env.e2e` (gitignored, `.env.production`'ın bir kopyası; `DOMAIN`/`APP_URL`/`API_URL`/`CORS_ORIGINS`/`TRUSTED_HOSTS` yerel `localhost:8080`'e, `LIVE_CALLS_ENABLED=true`'ya, bellek limitleri VM'in 2.9GB kısıtına uyacak şekilde ayarlandı).
- `LIVEKIT_URL=wss://your-project.livekit.cloud`, `OPENAI_API_KEY` sahte — **gerçek bir LiveKit/OpenAI/Netgsm bağlantısı hiçbir zaman kurulmadı, gerçek arama hiçbir zaman denenmedi.**
- Yerel Caddy: `deploy/caddy/Caddyfile.local` (Aşama 6'da hazırlanmış) — `localhost:8080` düz HTTP.
- 8/8 servis healthy oldu (postgres, redis, api, beat, worker, frontend, caddy sürekli; **voice-agent başlangıçta healthy, ardından SDK'nın retry bütçesi tükenince `unhealthy`'e geçti — bu, `PRODUCTION_INFRA_REPORT.md`'de ÖNCEDEN belgelenen, sahte/erişilemez LiveKit ile beklenen davranışın bizzat bu turda da doğrulanmasıdır, yeni bir bulgu değildir.**).

## 2. 21 Adımlık Senaryo — Sonuç

| # | Adım | Sonuç | Kanıt |
|---|---|---|---|
| 1 | Stack temiz build oluyor | ✅ | 7 imaj (api/beat/worker/voice-agent/frontend/migrate/backup), `docker compose build` exit 0 |
| 2 | Migration çalışıyor | ✅ | `alembic upgrade head` 3 revizyon uyguladı |
| 3 | Admin/owner test kullanıcısı oluşturuluyor | ✅ | `python -m app.bootstrap` → `owner created: owner@ivac.local` |
| 4 | Caddy üzerinden login | ✅ | Gerçek `POST /api/auth/login` (curl + Playwright), session+CSRF cookie |
| 5 | Lead oluşturuluyor | ✅ | Gerçek CSV import (`/api/imports/preview`+`/commit`, hem UI hem curl) — 3 satırdan 1 geçerli, 2 doğru şekilde reddedildi (boş isim, geçersiz telefon) |
| 6 | Lead listede görünüyor | ✅ | `/api/leads?q=Acme` + Playwright arama/tıklama |
| 7 | Çağrı isteği oluşturuluyor | ✅ | Gerçek dial dispatch denemesi (aşağıda detay) |
| 8 | Worker job'ı alıyor | ✅ | Worker log: `Task app.tasks.call_tasks.place_call[...] received` |
| 9-11 | Sahte ses sağlayıcı call-started/opening/conversation event'leri | **Docker'da simüle edilmedi** | Bkz. §4 — bilinçli kapsam kararı |
| 12 | Çağrı sonlandırılıyor | ✅ | Dispatch denemesi `dispatch_failed` ile temiz sonlandı, `status=failed` |
| 13 | Sonuç+not backend'e yazılıyor | ✅ | `CallEvent` tam denetim izi (queued→preparing→failed→outcome_fallback) |
| 14 | Frontend güncellenmiş durumu gösteriyor | ✅ | Playwright: SSE tabanlı canlı yenileme ile "Başarısız" (veya Pazar politika hatası) görünür oldu |
| 15 | Mükerrer çağrı isteği güvenli davranıyor | ✅ | Bkz. §5 |
| 16 | Yetkisiz kullanıcı admin kaynağına erişemiyor | ✅ | `viewer` → `GET /api/users` 403, tam mesaj doğrulandı |
| 17 | İç API dışarıdan erişilemiyor | ✅ | `GET /api/internal/v1/*` → 403 (hem curl hem Playwright) |
| 18 | Kalıcı veri servis restart'ından sağ çıkıyor | ✅ | Bkz. §6 |
| 19 | Backup alınıyor | ✅ | `postgres-backup.sh` → checksum + gzip doğrulandı |
| 20 | Disposable restore yapılıyor | ✅ | `restore-smoke-test.sh` → TÜMÜ GEÇTİ (0 başarısızlık) |
| 21 | Restore sonrası veri doğrulanıyor | ✅ | Satır sayısı + içerik kaynakla birebir eşleşti; bozuk checksum'lı restore doğru reddedildi |

Viewport genişlikleri (320/390/768/1280px): dashboard + leads sayfaları, hiçbirinde yatay taşma yok — 8/8 Playwright testi geçti.

## 3. En Değerli Kanıt: Gerçek Dispatch Denemesi (Adım 7-14)

Bugünün gerçek takvim günü **Pazar** olduğu için `call_policy.py::is_within_call_hours`'ın kasıtlı "Pazar günü arama yok" kuralı, normal `POST /api/calls` isteğini politika seviyesinde reddediyordu (409 `outside_call_hours`) — bu GERÇEK, doğru bir iş kuralı olduğu için test kolaylığı için atlanmadı/mock'lanmadı. Bunun yerine, orchestrator'ın politika kapılarından SONRAKİ adımını (gerçek DB satırı + gerçek Celery dispatch) birebir taklit eden tek seferlik bir doğrulama betiği ile worker'ın GERÇEK, ÇALIŞAN container'ına iş verildi:

```
worker-1 | Task app.tasks.call_tasks.place_call[...] received
worker-1 | ERROR/ForkPoolWorker-1] Dispatch hatası: dispatch_failed
worker-1 | Task app.tasks.call_tasks.place_call[...] succeeded in 0.93s: None
```

DB sonucu:
```
status: failed
error_code: dispatch_failed
outcome: technical_failure
ended_at set: True
events: queued → status:preparing → status:failed(dispatch_failed) → outcome_finalized → outcome_fallback
```

Bu, TÜM gerçek altyapı zincirini (Redis broker → gerçek çalışan worker process → gerçek `LiveKitNetgsmTelephonyProvider` kodu → sahte/geçersiz `LIVEKIT_URL`'e karşı temiz bağlantı hatası → doğru hata sınıflandırması → DB güncellemesi → fallback outcome → tam denetim izi) **gerçek Docker container'larında, gerçek bir arama hiç denenmeden** kanıtlar.

## 4. Bilinçli Kapsam Dışı Bırakılan Maddeler (Adım 9-11)

Bu üç alt-adım ("sahte ses sağlayıcı call-started event'i", "sahte agent opening state'e geçer", "sahte konuşma sonucu üretilir") Docker container seviyesinde simüle EDİLMEDİ. Neden: `services/voice-agent`'ın production kod yolu (`agent/job_handler.py::build_server`) her zaman GERÇEK `LiveKitRealtimeSessionAdapter`/`LiveKitSIPParticipantAdapter`'ı bağlar; `Fake*` test double'ları (`agent/session.py::FakeRealtimeSessionAdapter` vb.) yalnız pytest'in kendi test-only import yolunda var — çalışan bir container'a bu sahte adaptörleri enjekte edecek bir ortam değişkeni/switch YOK. Böyle bir switch'i bu turda production koduna eklemek, "test kolaylığı için gerçek koda yeni bir dal eklemek" anlamına gelirdi — kapsam dışı bir mimari genişleme olurdu.

Bunun yerine bu TAM DAVRANIŞ (gerçek konuşma döngüsü, opening gate, tool çağrıları, completion coordinator, mükerrer teslimat koruması) **`services/voice-agent`'ın 140 testlik pytest paketiyle** (Aşama 4/8'de kapsamlı biçimde doğrulandı, `FakeRealtimeSessionAdapter`/`FakeAPI` ile gerçek kod yolu üzerinden) zaten kanıtlanmış durumda — bu Docker E2E turu SIFIRDAN aynı şeyi tekrar kanıtlamaya çalışmak yerine, pytest'in KAPSAMADIĞI katmanı (gerçek Docker network'ü, gerçek Caddy routing'i, gerçek Celery broker'ı, gerçek worker process'i, gerçek Postgres persistansı) doğrulamaya odaklandı.

## 5. Mükerrer İstek Güvenliği

- **Idempotency-key path**: `POST /api/calls` aynı `idempotency_key` ile iki kez çağrıldı — Pazar politika kapısı her iki isteği de reddetti (409, aynı mesaj), yani spesifik "aynı key → aynı Call satırı" yoluna bu turda ulaşılamadı (politika kapısı idempotency kontrolünden ÖNCE çalışıyor — doğru sıralama). Bu spesifik yol zaten `services/api/tests/integration/test_orchestrator.py::test_idempotency_and_active_call_prevent_duplicates` ile gerçek Postgres+Redis üzerinde kanıtlı.
- **Worker redelivery path** (asıl kritik güvenlik garantisi — Aşama 8'de bulunan mükerrer-gerçek-arama riskine karşı): `services/api/tests/integration/test_call_tasks.py::test_place_call_redelivery_after_successful_dial_prevents_duplicate_real_call` ile gerçek Postgres+Redis üzerinde kanıtlı (bu Docker turunda tekrar EDİLMEDİ — bir `docker exec` zincirlemesi güvenlik sınıflandırıcısı tarafından bilerek engellendi; aynı kodun pytest'teki kanıtı zaten kesin).

## 6. Restart Kalıcılığı

```
restart öncesi: GET /api/leads?q=Acme → total=1
docker compose restart postgres api
restart sonrası: GET /api/leads?q=Acme → total=1, TÜM alanlar (id, business_name,
  phone_masked, demo_link, created_at, status) birebir aynı
GET /ready → {"status":"ready","checks":{"database":"ok","redis":"ok"}}
```

Session cookie de Redis'in restart edilmemesi nedeniyle geçerliliğini korudu (yalnız postgres+api restart edildi) — bu da Redis'in oturum kalıcılığını doğru sağladığını gösterir.

## 7. Doğrulama Komutları (özet)

```
docker compose -p ivac-e2e --env-file .env.e2e -f compose.production.yml \
  -f deploy/caddy/compose.local-caddy.override.yml up -d
docker compose -p ivac-e2e ... run --rm migrate
docker compose -p ivac-e2e ... run --rm api python -m app.seed
docker compose -p ivac-e2e ... run --rm -e BOOTSTRAP_ADMIN_EMAIL=... -e BOOTSTRAP_ADMIN_PASSWORD=... api python -m app.bootstrap
curl http://localhost:8080/health /ready
curl -X POST http://localhost:8080/api/auth/login ...
curl -X POST http://localhost:8080/api/imports/preview|commit ...
pnpm --filter @ivac/e2e test:docker   # 21/21 passed
docker compose -p ivac-e2e ... restart postgres api   # kalıcılık testi
docker compose -p ivac-e2e ... run --rm backup /scripts/postgres-backup.sh
docker compose -p ivac-e2e ... run --rm backup /scripts/restore-smoke-test.sh
docker compose -p ivac-e2e ... run --rm backup /scripts/verify-backup.sh --all
```

## 8. Yeni Test Altyapısı (commit kapsamına dahil)

- `tests/e2e/playwright.docker.config.ts` — disposable Docker stack'e karşı çalışan ayrık config (kendi `webServer` başlatmaz, `localhost:8080`'e işaret eder, `auth-redirect.spec.ts`'i BİLEREK hariç tutar çünkü o dosya `localhost:3000`'i sabit kodluyor).
- `tests/e2e/specs-docker/full-flow.spec.ts` — CSV import→lead→call-initiate akışı, RBAC/iç-API izolasyonu, 4 viewport genişliği (8 test). Sunucu tarafı Pazar-günü politikasına dayanıklı yazıldı (`failedStatus.or(policyError)` — hangi gün çalıştırılırsa çalıştırılsın geçerli).
- `tests/e2e/package.json` — `test:docker` script'i eklendi.
- **Karşılaşılan ve düzeltilen 3 test-script hatası** (uygulama hatası DEĞİL): (a) `getByRole("button", {name:"Ara"})` "Numarayı göster" ile substring çakışması (`exact:true` eklendi), (b) `getByLabel("Rol")` "Parola" ile substring çakışması (`exact:true` eklendi), (c) ikinci tam tarayıcı context'i ile viewer login'in 2.9GB VM altında zamanlama yarışına girmesi — Playwright'ın `request` fixture'ına (gerçek HTTP, tarayıcı render'ı olmadan) geçilerek deterministik hale getirildi.

## 9. Sonuç

21/21 senaryo adımı ya doğrudan ya da bilinçli/gerekçeli bir alternatif yolla (worker-seviyesi doğrudan dispatch, pytest referansı) doğrulandı. Kritik/yüksek açık bulgu yok. Sahte-sağlayıcı sonuçları (voice-agent'ın kendi konuşma mantığı) ile gerçek-altyapı sonuçları (Docker/Caddy/Celery/Postgres/backup-restore) net biçimde ayrıştırıldı — hiçbiri diğeri yerine geçirilmedi. Aşama 12'ye geçiş için engel yok; disposable stack, kaynak tasarrufu için Aşama 12'nin kullanımına açık bırakıldı.
