# Aşama 10 — Observability ve Operasyon

Tarih: 2026-07-19
Kapsam: Aşama 9 commit (`5b1cd5f`) sonrası; mimariye dokunmadan operasyonel görünürlük denetimi ve tamamlanması.

## 1. Yöntem

Aşama 6-9'da zaten kurulmuş olan gözlemlenebilirlik altyapısı (yapılandırılmış JSON loglama, request-id/call-id korelasyonu, `/health`+`/ready`, backup durum dosyaları, log rotasyonu) doğrudan kod okunarak envanterlendi. Ardından görev tanımındaki 8 operasyonel soru tek tek "sistem bunu şu an cevaplayabiliyor mu?" sorusuyla test edildi; cevaplanamayanlar için minimal, mevcut araçları yeniden kullanan eklemeler yapıldı.

## 2. Sekiz Operasyonel Sorunun Durumu

| Soru | Önceki durum | Bu turdaki eklemeler |
|---|---|---|
| Bir servis neden unhealthy? | `make prod-health` (container durumu) + her serviste gerçek healthcheck (Postgres `pg_isready`, Redis `PING`, API `/health`, worker `celery inspect ping`, beat pidfile) | `make ready-check` — API'nin `/ready` uç noktasının DB+Redis alt kontrol JSON'unu tek komutla gösterir (önceden yalnız container-seviyesi health görünürdü, HANGİ bağımlılığın `not ok` olduğu görünmüyordu) |
| Son başarılı backup ne zaman? | `make backup-status` (local + off-site AYRI zaman damgaları) — zaten vardı, değişmedi | — |
| Hangi çağrı neden başarısız oldu? | `Call.error_code`/`disconnect_reason` alanları + `CallEvent` tablosu (`status:failed` event'i `reason` payload'ıyla), `/api/calls/{id}` detay uç noktası | — |
| Worker job'ı aldı mı? | Yalnız `celery inspect ping` (worker CANLI mı, ama HANGİ görevi işlediği görünmüyordu) | `make queue-status` — `celery inspect active`/`reserved` ile worker'ın şu an hangi görevleri işlediği/kuyrukta beklettiği görünür oldu |
| Retry oldu mu? | Kod okumadan cevaplanamazdı | `docs/production/OPERATIONS_RUNBOOK.md`'ye yeni bölüm: `place_call` Celery seviyesinde OTOMATİK RETRY yapmaz (bilinçli tasarım, `PHASE_8_RESILIENCE_REPORT.md`), redelivery güvenli (mükerrer dial önleme), en kötü durumda watchdog ~15dk içinde temizler — hepsi tek bir runbook bölümünde açıklandı |
| İsteğin request ID'si neydi? | `X-Request-ID` header + `request_id_var` → her log satırında `request_id` alanı (`app/core/logging.py::JsonFormatter`) — zaten vardı | — |
| Hata dış-servis mi uygulama mı? | `TelephonyError.code`/`CallPolicyError.code` gibi ayrık, makine-okunur hata kodları vs. sınıflandırılmamış exception'lar — zaten ayrık logluyordu | — |
| Secret/PII loglandı mı? | Aşama 8'de backend redaksiyon regex'i düzeltildi (Bearer/OpenAI-key/e-posta artık yakalanıyor), voice-agent'ın redaksiyonu zaten kanıtlanmıştı | — |

## 3. Yapılan Değişiklikler

### `Makefile` — 3 yeni hedef

- **`ready-check`**: `/ready` uç noktasını (API image'ının kendi healthcheck'inde zaten kullanılan Host-header-uyumlu python/urllib deseniyle) container içinden sorgulayıp JSON'u basar.
- **`queue-status`**: `celery -A app.worker.celery_app inspect active`/`reserved` — worker'ın şu an ne işlediğini/kuyrukta ne beklettiğini gösterir.
- **`doctor`**: tek komutla `prod-health` + `ready-check` + `backup-status`'u sırayla çalıştıran kompozit teşhis — yeni bir soyutlama/araç eklemedi, yalnız mevcut 3 hedefi zincirledi.

Tüm yeni `exec` çağrılarına `-T` eklendi (TTY olmayan/scriptlenmiş çağrı bağlamlarında `docker compose exec`'in başarısız olmaması için — mevcut Makefile'da daha önce hiç `exec` kullanılmıyordu, yalnız `run --rm` kullanılıyordu).

### `docs/production/OPERATIONS_RUNBOOK.md` — 2 yeni bölüm

1. **"Hızlı teşhis"** (dosyanın başına): `make doctor`/`ready-check`/`queue-status`'a işaret eder.
2. **"Bir çağrı QUEUED'da takılı kaldı / worker job'ı almıyor gibi görünüyor"**: önceden bu senaryo için hiçbir runbook bölümü YOKTU — şimdi `queue-status` ile teşhis adımları, retry davranışının bilinçli tasarımı, mükerrer-dial-önleme garantisi ve watchdog'un en-kötü-durum temizlik süresi (~15dk) tek yerde açıklanıyor.

## 4. Doğrulama

| Kontrol | Sonuç |
|---|---|
| `docker compose --env-file .env.production -f compose.production.yml config -q` | Geçti (Makefile/doc-only değişiklik, compose dosyasına dokunulmadı) |
| `make -n doctor` / `make -n ready-check` / `make -n queue-status` | Sözdizimi doğru, beklenen komut zincirini üretiyor |
| `make help` | Yeni 3 hedef listede görünüyor |

Bu turda hiçbir Python/TypeScript kodu değişmedi (yalnız `Makefile` + `docs/production/OPERATIONS_RUNBOOK.md`) — backend/frontend/voice-agent test paketleri bu yüzden yeniden çalıştırılmadı; Aşama 9 sonundaki temiz durumları (192/140/35 passed) geçerliliğini koruyor. Yeni `make doctor`/`ready-check`/`queue-status` hedeflerinin GERÇEK bir çalışan stack'e karşı canlı çalıştırılması, Aşama 11'in disposable stack'i ayağa kaldırdığı adımda dolaylı olarak doğrulanacak (mükerrer Docker build/up döngüsünden kaçınmak için burada tekrarlanmadı).

## 5. Bilinçli Olarak Eklenmeyenler

- Ücretli/zorunlu bir SaaS gözlemlenebilirlik platformu, ağır telemetri (OpenTelemetry vb.) veya dağıtık izleme — görev tanımı bunu açıkça yasakladı, mevcut yapılandırılmış JSON loglar + healthcheck'ler zaten sorulan operasyonel soruları cevaplıyor.
- Disk kullanımı için otomatik dashboard/alert — mevcut runbook zaten `df -h` + log-rotasyon sınırları (`max-size: 10m, max-file: 5`) ile bunu kapsıyor; yeni bir araç eklemek kapsam dışı bir genişleme olurdu.

## 6. Sonuç

Sekiz operasyonel sorunun tamamı artık ya doğrudan mevcut araçlarla ya da bu turda eklenen 3 hafif `make` hedefiyle cevaplanabiliyor. Mimariye hiçbir değişiklik yapılmadı. Aşama 11'e geçiş için engel yok.
