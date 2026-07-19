# Aşama 7 — Fonksiyonel Tamlık Denetimi

Tarih: 2026-07-19
Kapsam: Aşama 6 commit (`ae5adf9`) sonrası, kritik kullanıcı akışlarının uçtan uca gerçek backend davranışına sahip olup olmadığının denetimi.

## 1. Yöntem

- Read-only bir keşif ajanı ile 10 alan (auth/RBAC, lead CRUD, çağrı yaşam döngüsü, dashboard metrikleri, boş/hata/yükleniyor durumları ve sahte veri taraması, idempotency, sayfa-yenileme sonrası state, worker/queue davranışı, HTTP 200 arkasında gerçek etki olmayan uç nokta taraması, mevcut test kapsamı) tarandı.
- Ajanın bulguları üzerinden şüpheli/eksik görünen noktalar bizzat dosya bazında yeniden doğrulandı (aşağıda "Doğrulama" bölümü).
- Gerçek backend/frontend kontrolleri (Ruff, MyPy, pytest, tsc, ESLint, Vitest) bu turda yapılan değişiklik sonrası tekrar çalıştırıldı.

## 2. Genel Sonuç

Kod tabanı olgunluğu yüksek: önceki denetim turlarının (`CODEX_AUDIT_*`, `CODEX_REAUDIT_*`, `CODEX_FINAL_AUDIT_*`) kalıntısı olan sağlam RBAC, gerçek DB-destekli CRUD, gerçek Celery+Redis worker ve gerçek idempotency katmanları doğrulandı. **Sahte/stub production davranışı, kör buton, iş yapmadan 200 dönen uç nokta bulunmadı.**

## 3. Alan Bazlı Bulgular

| # | Alan | Durum | Not |
|---|------|-------|-----|
| 1 | Login/logout/RBAC/yetkisiz erişim | REAL | Ayrık bir `/refresh` uç noktası yok; bunun yerine `load_session()` her çağrıda Redis TTL'sini kayan pencereyle uzatıyor (`services/api/app/core/security.py:82-96`) — bilinçli tasarım, eksik değil. |
| 2 | Lead CRUD + filtre/sayfalama/arama | REAL (R+U, C+D yok) | Lead'ler yalnız toplu import ile oluşturuluyor (`app/api/routes/lead_import.py`), hard-delete yok — durum değişimi (`do_not_call` vb.) var. Frontend'de de tekil "lead oluştur/sil" arayüzü yok — tutarlı, kasıtlı tasarım. |
| 3 | Çağrı yaşam döngüsü (initiate/status/hangup/result/not) | REAL | `orchestrator.py::initiate_call` idempotency-key kısa devresi + Redis lock + aktif-çağrı kontrolü; watchdog (`call_tasks.py`) takılı çağrıları zorla kapatıyor. |
| 4 | Dashboard metrikleri | REAL | `system.py::dashboard_stats` gerçek SQL aggregation (SUM/COUNT), Europe/Istanbul gün sınırı. `test_system_api.py::test_dashboard_reflects_call_cost_and_outcomes` maliyet/outcome/süre matematiğini birim testiyle doğruluyor (ilk keşif turunda bu test gözden kaçmıştı, bu turda dosya doğrudan okunarak teyit edildi). |
| 5 | Boş/hata/yükleniyor durumları, sahte veri | REAL | `apps/web/{app,lib,components}` ve `services/api/app` genelinde `mock/fake/dummy/TODO/FIXME/NotImplementedError` taraması temiz (tek isabet: `config.py`'deki placeholder-secret reddetme listesi, veri değil). `NotWiredState` bileşeni tanımlı ama hiçbir sayfada kullanılmıyor — yani hâlâ "gerçek veri yok" durumuna düşmüş bir sayfa yok. |
| 6 | Duplicate/idempotency | REAL, 1 küçük boşluk kapatıldı | Kampanya çağrıları ve voice-agent↔API webhook olayları zaten deterministik idempotency key kullanıyordu (`campaign_tasks.py:89`, `internal_contract.py::idempotent`). Elle "Ara" butonu ise `idempotency_key` göndermiyordu — Redis lock + aktif-çağrı kontrolü ile fiilen korunsa da metin-kitabı idempotency-key deseni eksikti. **Bu turda düzeltildi** (bkz. §4). |
| 7 | Sayfa yenileme sonrası state | REAL | Tüm state React Query üzerinden server-kaynaklı; SSE yalnızca "refetch tetikleyici" olarak kullanılıyor (`use-live-events.ts:14-24`), UI state'i SSE payload'ından türetilmiyor — refresh'te kaybolacak yetkili state yok. |
| 8 | Worker/queue davranışı | REAL, doğrulandı | Celery+Redis, `task_acks_late=True` + `worker_prefetch_multiplier=1`. `services/worker/` dizini boş olsa da hem `Makefile:48-52` hem `compose.production.yml:221` gerçek komutu (`celery -A app.worker.celery_app worker/beat`) doğru şekilde çalıştırıyor — **bu turda bizzat doğrulandı, wiring sorunu yok**. `place_call` Celery seviyesinde retry yapmıyor (`max_retries=0`) — kasıtlı, redial mantığı `call_policy.py::compute_next_retry` üzerinden kampanya katmanında. |
| 9 | Gerçek etkisiz 200 dönen uç noktalar | REAL, 3 dosya bizzat tekrar okundu | `campaigns.py`, `content.py`, `services/api/app/api/routes/internal/tools.py` ilk keşif turunda yalnız grep'lenmişti; bu turda tam okundu — hepsi gerçek DB yazımı/okuması yapıyor, stub yok. `end_call_safely` niyet kaydediyor (`should_hangup=true, hangup_performed=false`) ve gerçek kapanışı agent'ın grace-period state makinesine bırakıyor — bu davranış Aşama 8'de resilience açısından ayrıca değerlendirilecek. |
| 10 | Mevcut test kapsamı | Büyük ölçüde REAL | Backend unit+integration+E2E-adjacent testler kapsamlı. **Bilinen boşluk:** Playwright E2E specs yalnız auth+dashboard+navigation kapsıyor; lead→çağrı başlat→canlı görüntüle→sonuç akışı için tıklama seviyesinde E2E yok. Bu, Aşama 11'in ("Tam disposable E2E", 21 adımlı senaryo) kapsamına bilerek bırakıldı — mükerrer iş yapılmadı. |

## 4. Bu Turda Yapılan Değişiklik

**Dosya:** `apps/web/app/(app)/leads/[id]/page.tsx`

Manuel "Ara" butonu artık `crypto.randomUUID()` ile üretilmiş bir `idempotency_key` gönderiyor:

```ts
const call = await initiateCall.mutateAsync({
  lead_id: lead.id,
  idempotency_key: crypto.randomUUID(),
});
```

- Backend şeması zaten bu alanı destekliyordu (`apps/web/lib/api/schemas.ts:580`, `callInitiateRequestSchema`), backend orchestrator zaten kısa devre mantığına sahipti (`orchestrator.py:66-71`) — yalnızca client bunu göndermiyordu.
- Risk: düşük, geriye dönük uyumlu (alan zaten opsiyonel), tek çağrı sitesi (`grep` ile doğrulandı — `apps/web/app` içinde `useInitiateCall` yalnız bu sayfada kullanılıyor).
- Bilinçli olarak yeni bir test-harness/dosya oluşturulmadı: bu sayfa için hâlâ hiçbir component-level render testi yok (yalnızca `status-badge.test.tsx` gibi izole bileşen testleri mevcut) ve tam bir sayfa testi (QueryClientProvider + router mock + apiRequest mock) kurmak, tek satırlık bir alan eklemesine göre orantısız bir kapsam genişlemesi olurdu. Bu davranış zaten Aşama 11'in gerçek tarayıcı E2E akışında (lead → çağrı başlat → canlı görüntüle) dolaylı olarak doğrulanacak.

## 5. Doğrulama (bu turda çalıştırıldı)

| Kontrol | Sonuç |
|---|---|
| `apps/web` — `tsc --noEmit` | Temiz |
| `apps/web` — `eslint app/(app)/leads/[id]/page.tsx` | Temiz |
| `apps/web` — `vitest run` | 5 dosya / 35 test PASS |
| `services/api` — `ruff check app tests` | Temiz |
| `services/api` — `mypy app` | Temiz (81 dosya) |
| `services/api` — `pytest -q` | 160 passed |
| Worker komutu doğrulaması | `Makefile:48-52` ve `compose.production.yml:216-222` her ikisi de `app.worker.celery_app` çağırıyor — dev ve production tutarlı. |

Voice-agent bu turda değiştirilmedi; Aşama 6 commit'inden sonraki durumu (117 passed, ruff+mypy temiz) geçerliliğini koruyor.

## 6. Bilinçli Olarak Ertelenen / Kapsam Dışı Bırakılan Maddeler

1. **Lead tekil oluşturma/silme UI'sinin olmaması** — mevcut ürün tasarımının (toplu import + soft-delete) bilinçli bir parçası gibi görünüyor; kullanıcıdan (Kadir) ayrıca teyit istenmeden "eksik" olarak işaretlenip yeni bir CRUD yüzeyi eklenmedi. Bu bir varsayımdır; ürün gereksinimleri değişirse ayrı bir talep olarak ele alınmalı.
2. **`end_call_safely`'nin gerçek hangup'ı hemen tetiklememesi** — Aşama 8'in (dayanıklılık/hata yönetimi) kapsamına daha uygun; şimdi dokunulmadı.
3. **Leads/çağrı/kampanya akışları için tıklama seviyesinde Playwright E2E'nin eksikliği** — Aşama 11'in doğrudan görev tanımı; burada mükerrer olmaması için atlandı.

## 7. Sonuç

Kritik/yüksek veya commit-engelleyici orta seviye fonksiyonel bulgu **yok**. Bir küçük idempotency-hijyen boşluğu kapatıldı. Aşama 8'e geçiş için engel yok.
