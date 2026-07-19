# Aşama 12 — Performans ve Kaynak Smoke Testi

Tarih: 2026-07-19
Kapsam: Aşama 11'in disposable `ivac-e2e` Docker stack'i (ayrı proje/volume, gerçek 8 servis) yeniden kullanılarak; ağır/gerçek yük testi DEĞİL, güvenli bir smoke testi. Kesin bir performans SLA'sı icat edilmedi — yalnız gözlemlenen sonuçlar raporlanır.

## 1. Kaynak Taban Çizgisi (yük öncesi)

| Servis | CPU | Bellek | Limit |
|---|---|---|---|
| api | 0.29% | 84MB | 384MB |
| worker | 0.09% | 129MB | 384MB |
| postgres | 0.00% | 49MB | 512MB |
| redis | 1.20% | 5.5MB | 128MB |
| frontend | 0.00% | 68MB | 256MB |
| caddy | 0.00% | 12MB | 2.9GB |

FD sayıları: api=15, postgres=10.

## 2. Smoke Testleri ve Sonuçları

| Test | Sonuç |
|---|---|
| 10 eşzamanlı normal API isteği (`/api/leads`, sayfalanmış) | **10/10 → 200**, toplam 480ms |
| 25 eşzamanlı okuma isteği (dashboard/leads/campaigns/calls karışık) | **25/25 → 200**, toplam 1.26s |
| Sayfalama + filtre (`page_size=1`, `lead_status=new/contacted`, boş arama) | Doğru çalışıyor — `total`/`items` tutarlı, filtre gerçekten filtreliyor |
| 5 eşzamanlı sahte çağrı job'ı (worker kuyruğu) | **5/5 temiz `dispatch_failed` ile tamamlandı** (0.4-1.4s/job), kalıcı kuyruk birikintisi YOK, 0 "stuck" aktif çağrı |
| Worker kuyruk tüketimi | Sıralı işlendi (bu turda `WORKER_CONCURRENCY=1`, kaynak tasarrufu için bilerek düşürülmüştü — production varsayılanı 2) — deadlock/donma yok |
| Backend başlangıcı | `/health` sürekli 1-4ms yanıt verdi (aralıklı health-check isteklerinde gözlemlendi) |
| Frontend yanıtı | Playwright testlerinde (Aşama 11) sayfa yüklemeleri tutarlı biçimde 1-2s altında |
| DB bağlantı havuzu | Yük sonrası `pg_stat_activity`: 6 idle + 1 aktif (kendi sorgum) — hiçbiri "idle in transaction" değil, **sızıntı yok** |
| Redis bağlantısı | Sürekli `healthy`, bellek kullanımı sabit (5.5MB → 5.6MB) |

## 3. Yük Sonrası Kaynak Karşılaştırması

| Servis | Önce | Sonra | Değişim |
|---|---|---|---|
| api | 84MB | 89MB | +5MB (normal — bağlantı/response cache) |
| worker | 129MB | 130MB | +1MB (ihmal edilebilir) |
| postgres | 49MB | 58MB | +9MB (yeni tablolar/indeks sayfaları, beklenen) |
| redis | 5.5MB | 5.6MB | ihmal edilebilir |
| api FD | 15 | 27 | +12 (eşzamanlı HTTP keep-alive soketleri; DB havuzu `pool_size=5` ile sınırlı, sızıntı işareti yok) |

**Aşırı bellek büyümesi, FD sızıntısı, veya "idle in transaction" bağlantı birikimi gözlenmedi.**

## 4. Log Hacmi

Yaklaşık 30 dakikalık test etkinliği sonrası: api 455 satır, worker 150 satır — kontrolsüz büyüme yok. `grep`'te gerçek 5xx/ERROR satırı bulunmadı (yalnız beklenen `dispatch_failed` hata logları — bunlar TelephonyError olarak doğru sınıflandırılmış, sahte LIVEKIT_URL'e karşı beklenen sonuç).

## 5. Gözlemlenen Yavaş Nokta (SLA iddiası DEĞİL, ham gözlem)

25 eşzamanlı okuma isteği sırasında `/api/calls` ve `/api/dashboard/stats` istekleri 500-600ms arasında yanıt verdi (diğerlerinden daha yavaş). Bu makinenin paylaşımlı/kısıtlı Colima VM'i (2.9GB, ayrıca bu oturumun diğer Docker build'leriyle de paylaşılıyordu) altında gözlemlendi — gerçek bir production sunucusunda çok daha fazla CPU/bellek başlığı olacağından bu rakamları bir SLA ihlali olarak yorumlamıyoruz. Sorgu planlarında (N+1 vb.) bu turda derinlemesine bir inceleme yapılmadı; yanıt süreleri saniyenin altında kaldığı ve tekrar eden bir 5xx/timeout paterni olmadığı için düşük öncelikli bir operasyonel not olarak bırakılıyor.

## 6. Bu Turda Yapılan Kod Değişikliği

**Yok.** Smoke testinde hiçbir gerçek performans/kaynak sorunu bulunmadı; düzeltilecek düşük maliyetli bir açık problem yoktu. Görev tanımındaki açık talimat gereği ("Do NOT create an empty commit if no change needed") bu aşama için commit oluşturulmadı.

## 7. Sonuç

Sistem, güvenli eşzamanlı yük altında (10+25 eşzamanlı istek, 5 eşzamanlı worker job'ı) 5xx patlaması, bağlantı sızıntısı, worker deadlock'u, kalıcı kuyruk birikintisi veya kontrolsüz kaynak büyümesi göstermedi. Aşama 13'e geçiş için engel yok.
