# Go-Live Checklist

Bu, **yalnızca teknik** bir kontrol listesidir. KVKK/arama izni, ticari sözleşme, marka onayı gibi hukuki/iş gereksinimlerini KAPSAMAZ — bunlar ayrı, insan onaylı bir süreçte ele alınmalıdır. Bu listedeki hiçbir madde "tamamlandı" işaretlenerek hukuki uyumluluk beyan edilmiş sayılmaz.

## Altyapı

- [ ] Production sunucu hazır (yeterli CPU/RAM/disk — bkz. `PHASE_12_PERFORMANCE_REPORT.md` gözlemleri, gerçek yük altında ayrıca ölçülmeli)
- [ ] Domain DNS gerçek sunucu IP'sine işaret ediyor
- [ ] Gerçek TLS sertifikası (Caddy ACME ile otomatik) alınmış ve doğrulanmış — `tls internal` KULLANILMIYOR
- [ ] 80/443 portları güvenlik duvarında açık, başka hiçbir port dışarıya açık DEĞİL

## Secret'lar

- [ ] `.env.production` gerçek, güçlü (20+ karakter) secret'larla dolu — `REPLACE_ME`/`example`/`dummy` gibi placeholder YOK
- [ ] `JWT_SECRET`/`COOKIE_SECRET`/`PII_ENCRYPTION_KEY`/`PHONE_HASH_PEPPER`/`INTERNAL_SERVICE_TOKEN` birbirinden FARKLI
- [ ] `INTERNAL_SERVICE_TOKEN` hem `api` hem `voice-agent` ortamında AYNI
- [ ] Secret'lar güvenli bir secret store'da yedekli (yalnız `.env.production` dosyasında değil)
- [ ] `.env.production` git'e commit edilmemiş (`git check-ignore -v .env.production` ile doğrulayın)

## Veritabanı

- [ ] PostgreSQL production'da çalışıyor, `pg_isready` healthy
- [ ] Migration'lar uygulanmış (`make prod-migrate`), `alembic current` HEAD'i gösteriyor
- [ ] İlk owner/admin kullanıcısı oluşturulmuş (`make prod-bootstrap-admin`)

## Redis

- [ ] Redis production'da çalışıyor, `REDIS_PASSWORD` ayarlı
- [ ] Redis'in kalıcı iş verisi TUTMADIĞI biliniyor (yalnız oturum/kilit/kuyruk — bkz. `docs/production/BACKUP_AND_RESTORE.md` §2)

## LiveKit / OpenAI / Netgsm

- [ ] Gerçek LiveKit projesi oluşturulmuş, API key/secret alınmış
- [ ] LiveKit SIP outbound trunk oluşturulmuş, `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` ayarlı
- [ ] Gerçek Netgsm hesabı, giden arama izni AÇIK
- [ ] Netgsm trunk LiveKit'e doğru bağlanmış (gerçek bir test çağrısıyla doğrulanmalı — bkz. `docs/PILOT_RUNBOOK.md`)
- [ ] Gerçek OpenAI API key, yeterli kota/limit
- [ ] Numara tahsisi/izinleri (hangi numaralar aranabilir, giden numara gösterimi) netleştirilmiş

## KVKK / Arama Politikası (yalnız işaretleme — hukuki onay ayrı süreçtir)

- [ ] Arama izin/açıklama metni hazır (bu checklist'in kapsamında DEĞİL, ayrı onay gerektirir)
- [ ] Suppression/DNC (aranmayacaklar) listesi mekanizması test edilmiş (`app/services/suppression_service.py`)
- [ ] Veri saklama politikaları (`TRANSCRIPT_RETENTION_DAYS`, `AUDIO_RETENTION_DAYS`) kuruluşun politikasıyla uyumlu ayarlanmış

## Off-site Backup

- [ ] `BACKUP_REMOTE_ENABLED=true`, `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` ayarlı
- [ ] **Gerçek bir off-site backup en az bir kez BAŞARIYLA tamamlanmış** (bu depodaki testler yalnız disposable/local ortamda yapıldı — bkz. `OPEN_OPERATIONAL_BLOCKERS.md`)
- [ ] Backup zamanlaması aktif (`deploy/systemd/ivac-postgres-backup.timer`)

## Restore Tatbikatı

- [ ] **Gerçek uzak (off-site) restore en az bir kez denenmiş** — yalnız local disposable restore bu depoda test edildi (`PHASE_11_E2E_REPORT.md`)
- [ ] Restore süresi ölçülmüş, kabul edilebilir bir RTO/RPO'ya karşılık geldiği doğrulanmış

## Alerting

- [ ] Servis unhealthy/down durumunda operatöre bildirim giden bir mekanizma var (bu depoda dahili bir alerting sistemi YOK — bkz. `OPEN_OPERATIONAL_BLOCKERS.md`)
- [ ] Backup başarısızlığı için bildirim mekanizması var
- [ ] Olay müdahale iletişim yolu belirlenmiş (bkz. `docs/INCIDENT_RESPONSE.md`)

## Log Redaksiyonu

- [ ] Production log çıktısı gözle kontrol edilmiş — telefon/e-posta/token/parola düz metin GÖRÜNMÜYOR (otomatik testler `PHASE_8_RESILIENCE_REPORT.md`'de var, gerçek trafikte de teyit edilmeli)
- [ ] Log rotasyonu aktif (`max-size: 10m, max-file: 5` — `compose.production.yml`)

## Pilot Çağrı

- [ ] En az bir gerçek pilot çağrı BAŞARIYLA tamamlanmış (`docs/PILOT_RUNBOOK.md`)
- [ ] Pilot sonrası backup alınmış ve doğrulanmış

## Rollback Hazırlığı

- [ ] Önceki stabil commit/tag biliniyor
- [ ] `docs/RELEASE_PROCESS.md`'deki rollback adımları test edilmiş (en azından disposable ortamda)

## Olay İletişimi

- [ ] Kim, ne zaman, hangi kanaldan haberdar edilecek belirlenmiş (bkz. `docs/INCIDENT_RESPONSE.md`)

---

**Bu checklist'in TAMAMI işaretlenmeden gerçek müşteri trafiğine (pilot dışı) geçilmemelidir.**
