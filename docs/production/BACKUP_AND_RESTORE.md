# BACKUP_AND_RESTORE.md

## 1. Nelerin Yedeklendiği

Gerçek kod okunarak çıkarılan kalıcı veri envanteri
(`PRODUCTION_INFRA_REPORT.md` §8'de tam gerekçesiyle):

| Veri | Nerede | Sınıflandırma | Yedekleniyor mu |
|---|---|---|---|
| Lead/kampanya/çağrı/kullanıcı/audit kayıtları | PostgreSQL | Mutlaka yedeklenmeli | **Evet** — bu dokümanın konusu |
| Çağrı transkriptleri | PostgreSQL `calls.transcript` (JSONB) | Mutlaka yedeklenmeli | **Evet** (Postgres backup'ının parçası — ayrı dosya YOK, kod okunarak doğrulandı: transkript diske yazılmıyor) |
| Şifreli telefon numaraları, audit log | PostgreSQL | Mutlaka yedeklenmeli | **Evet** |
| Redis (session, rate-limit, Celery broker/backend, SSE pub/sub) | Redis `appendonly` volume | Geçici/cache | **Hayır** (bkz. §2) |
| Caddy TLS sertifikaları | `caddy_data` volume | Yeniden oluşturulabilir | Hayır (Let's Encrypt'ten yeniden alınabilir; kaybı yalnız geçici bir yeniden-issue gecikmesine yol açar) |
| Ses kaydı / çağrı kaydı dosyaları | — | Henüz projede kullanılmıyor | Yok (`CALL_RECORDING_ENABLED` bayrağı var ama kod içinde LOKAL bir kayıt yazma yolu YOK — etkinleştirilirse LiveKit Egress'in kendi bulut hedefine yazması beklenir, bu compose'un kapsamı dışında) |
| Kullanıcı dosya yüklemeleri | — | Henüz projede kullanılmıyor | Yok (lead import dosyaları `io.BytesIO` ile bellekte işlenir, diske hiç yazılmaz — kod okunarak doğrulandı) |

## 2. Nelerin Yedeklenmediği (ve Neden)

**Redis yedeklenmiyor.** Kod okunarak doğrulandı (`app/worker.py`,
`app/core/redis.py`, `app/core/ratelimit.py`): Redis şu amaçlarla kullanılıyor:
- Celery broker/backend (görev kuyruğu) — kaybı, o an kuyrukta bekleyen
  birkaç dakikalık görevin (ör. henüz dispatch edilmemiş bir arama) kaybı
  anlamına gelir; kalıcı iş sonucu DEĞİLDİR.
- Oturum token'ları (`session:*`) — kaybı yalnız kullanıcıların yeniden giriş
  yapmasını gerektirir, veri kaybı DEĞİLDİR.
- Rate-limit sayaçları — kaybı geçicidir, kendi kendine sıfırlanır.
- SSE pub/sub kanalı — tamamen anlık, kalıcı değildir.

Bu nedenle Redis **"reconstructable/cache"** olarak sınıflandırıldı, ayrı bir
backup mekanizması KURULMADI. Dayanıklılık için `redis.conf`'ta `appendonly
yes` açık (compose'da tanımlı) — bu yalnız container/host restart'ında veri
kaybını azaltır, KASITLI bir felaket-kurtarma stratejisi DEĞİLDİR.

## 3. Local ve Off-site Backup Farkı

- **Local backup** (`postgres_backups` named volume, aynı Docker host'ta):
  hızlı restore, ama **sunucunun kendisi kaybolursa (disk arızası, sunucu
  silinmesi, yangın, çalınma) LOCAL BACKUP DA KAYBOLUR.**
- **Off-site backup** (`restic` ile S3-uyumlu uzak depolama): sunucudan
  BAĞIMSIZ bir yerde, şifreli olarak saklanır — gerçek felaket kurtarma
  senaryosunu karşılar.

**`BACKUP_REMOTE_ENABLED=false` iken (veya restic credential'ları eksikken)
sistem YALNIZ local backup alır ve bu AÇIKÇA "felaket kurtarma için hazır
DEĞİL, yalnız local-only backup" olarak değerlendirilmelidir** — bkz.
`PRODUCTION_INFRA_REPORT.md` §10, §18.

## 4. Retention

| Politika | Varsayılan | Env değişkeni |
|---|---|---|
| Local backup saklama | 14 gün | `BACKUP_RETENTION_DAYS` |
| Off-site günlük | 14 snapshot | `RESTIC_RETENTION_DAILY` |
| Off-site haftalık | 8 snapshot | `RESTIC_RETENTION_WEEKLY` |
| Off-site aylık | 6 snapshot | `RESTIC_RETENTION_MONTHLY` |

Local retention `postgres-backup.sh` içinde `find ... -mtime +N -delete` ile
her başarılı backup sonunda uygulanır. Off-site retention `restic forget
--prune` ile `offsite-backup.sh` içinde uygulanır.

## 5. Manuel Backup

```bash
make backup
```

Bu `docker compose run --rm backup /scripts/postgres-backup.sh` çalıştırır:
tutarlı `pg_dump` → gzip -9 → SHA-256 checksum → atomik yazım (`mv`) →
retention → (etkinse) off-site yükleme. Ayrıntılı davranış:
`scripts/backup/postgres-backup.sh` (kod yorumlarıyla belgelenmiştir).

## 6. Otomatik Backup

Host systemd timer (`deploy/systemd/ivac-postgres-backup.{service,timer}`):
her gün **UTC 03:15**'te `make backup` ile aynı komutu tetikler.
`Persistent=true` sayesinde sunucu o saatte kapalıysa görev ATLANMAZ,
sonraki açılışta gecikmeli çalışır. `RandomizedDelaySec=300` art arda
tetiklenmeyi önler. Kurulum: `docs/production/DEPLOYMENT.md` §18.

Manuel tetikleme: `make backup` (systemd timer'ı beklemeden).

Son başarılı backup zamanını denetleme:

```bash
make backup-status
# veya
systemctl status ivac-postgres-backup.timer
journalctl -u ivac-postgres-backup.service --since "2 days ago"
```

## 7. Checksum Doğrulama

Her backup dosyasının yanında `<dosya>.sha256` üretilir. Toplu doğrulama:

```bash
make backup-verify-all
```

Bu, `BACKUP_DIR` altındaki TÜM backup'ları checksum + gzip bütünlüğü + içerik
akıl sağlığı (`"PostgreSQL database dump"` imzası) açısından tarar.

## 8. Restore Ön Koşulları

- Checksum dosyası (`<backup>.sha256`) MUTLAKA mevcut ve doğru olmalı —
  yoksa/uyuşmuyorsa `postgres-restore.sh` restore'u BAŞLATMAZ.
- Hedef veritabanı adı AÇIKÇA belirtilmelidir (`--target-db`).
- `--force` bayrağı olmadan script HİÇBİR ŞEY yapmaz.
- Hedef, yapılandırılmış production DB adıyla (`PGDATABASE`) aynıysa AYRICA
  `--allow-production-overwrite` gerekir — bu, yanlışlıkla production'ın
  üzerine yazılmasını engelleyen bilinçli bir korumadır.

## 9. Disposable Restore Testi

```bash
make restore-smoke-test
```

`scripts/backup/restore-smoke-test.sh`: küçük test verisiyle bir kaynak DB
oluşturur → gerçek backup formatıyla yedekler → **gerçek
`postgres-restore.sh`'i çağırarak** disposable bir hedef DB'ye geri yükler →
veriyi doğrular → checksum'ı kasten bozup restore'un REDDEDİLDİĞİNİ
doğrular → tüm disposable kaynakları temizler. Gerçek production verisine
veya credential'a DOKUNMAZ.

**Düzenli olarak** (ör. ayda bir, önerilir) elle çalıştırılmalı — bir
backup'ın "var olması" onun "geri yüklenebilir olduğu" anlamına gelmez.

## 10. Production Restore Prosedürü

1. **DURUN VE DÜŞÜNÜN** — bu geri alınamaz bir işlemdir (hedef DB
   `--drop-existing` ile silinip yeniden oluşturulacaksa).
2. Mevcut durumun bir backup'ını alın (mümkünse): `make backup`.
3. Restore edilecek backup dosyasını ve checksum'ını belirleyin.
4. Uygulama trafiğini durdurun (`docker compose stop api worker beat
   voice-agent frontend` — `postgres`/`caddy` açık kalabilir).
5. Restore'u çalıştırın:
   ```bash
   docker compose -f compose.production.yml --env-file .env.production \
     run --rm backup /scripts/postgres-restore.sh \
     --backup-file /backups/ivac-postgres-YYYYMMDDTHHMMSSZ.sql.gz \
     --target-db ivac \
     --drop-existing \
     --allow-production-overwrite \
     --force
   ```
6. `make prod-migrate` çalıştırıp şemanın güncel olduğunu doğrulayın
   (restore edilen backup eski bir migration seviyesindeyse).
7. Uygulamayı yeniden başlatın: `make prod-up`.
8. Health kontrolü + panelde birkaç kayıt gözle doğrulayın.

## 11. Şifreleme Anahtarının Kaybının Sonuçları

- **`RESTIC_PASSWORD` kaybedilirse**: off-site repository'deki TÜM
  snapshot'lar KALICI OLARAK erişilemez hale gelir — restic şifrelemesi
  geri döndürülemez tasarlanmıştır, "parola sıfırlama" YOKTUR. Bu parolayı
  `.env.production`'dan AYRI, güvenli bir yerde (ör. şirket parola
  yöneticisi) de saklayın.
- **`PII_ENCRYPTION_KEY`/`PHONE_HASH_PEPPER` kaybedilirse**: PostgreSQL
  backup'ı geri yüklenebilir AMA şifreli telefon numaraları (`Lead.
  phone_ciphertext`) ARTIK ÇÖZÜLEMEZ — bu anahtarlar da backup'ın kendisi
  KADAR kritik, ayrı ve güvenli saklanmalıdır. Bu anahtarları PostgreSQL
  backup'ıyla AYNI yerde/sistemde saklamayın (ikisi birden ele geçirilirse
  şifrenin anlamı kalmaz; ikisi birlikte kaybedilirse veri kalıcı olarak
  okunamaz hale gelir).

## 12. Backup Başarısızlık Kontrolü

- `postgres-backup.sh` HERHANGİ bir adımda (pg_dump, gzip bütünlüğü, boş
  dosya, disk doluluğu, off-site yükleme) başarısız olursa **non-zero exit
  code** döner — systemd bunu `journalctl`'de "failed" olarak işaretler.
- `BACKUP_REMOTE_ENABLED=true` iken off-site yükleme başarısız olursa TÜM
  görev başarısız sayılır (yalnız local'e yazılıp "başarılı" gibi
  GÖRÜNMEZ).
- **Local ve off-site başarı zaman damgaları AYRI dosyalarda tutulur**
  (`.last-local-success` / `.last-remote-success`) — off-site etkinken
  YALNIZ `.last-remote-success`'a bakmak felaket-kurtarma hedefinin gerçekten
  güncel olduğunu doğrular; `.last-local-success` off-site başarısız olsa
  bile güncellenir ve tek başına yanıltıcıdır (bkz. `CODEX_AUDIT_PHASE_6.md`
  YÜKSEK-1 — bu oturumda düzeltildi).
- İzleme önerisi: `systemctl status ivac-postgres-backup.timer` veya
  `make backup-status`'u harici bir uptime/monitoring sisteminden periyodik
  kontrol edin; `BACKUP_REMOTE_ENABLED=true` iken `.last-remote-success`'ın
  (aksi halde `.last-local-success`'ın) yaşı bekleneni aşarsa alarm üretin.

## 13. Düzenli Restore Tatbikatı

`make restore-smoke-test`'i ayda en az bir kez çalıştırıp sonucunu
kayıt altına almanız ÖNERİLİR — "backup dosyası var" ile "backup gerçekten
geri yüklenebilir" farklı iddialardır; yalnız ikincisi test edilmiş bir
felaket kurtarma yeteneğidir.
