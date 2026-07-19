# OPERATIONS_RUNBOOK.md

Tüm komutlar `compose.production.yml --env-file .env.production` bağlamında
çalıştırılır; kısayollar için `make <hedef>` kullanılabilir.

## Hızlı teşhis (PHASE_10_OPERATIONS_REPORT.md)

Herhangi bir soruna bakmaya başlamadan önce: `make doctor` — container
durumu + `/ready` (DB+Redis alt kontrolleri) + son başarılı backup
zamanlarını TEK komutta gösterir. Ayrıca:
- `make ready-check` — yalnız `/ready` JSON çıktısı (hangi bağımlılık `not ok`?).
- `make queue-status` — Celery worker'ın hangi görevleri aktif/reserve
  tuttuğunu gösterir ("worker job'ı aldı mı?" sorusunun cevabı).

## Uygulama cevap vermiyor

1. `make prod-health` — hangi servis `unhealthy`/`Restarting`?
2. `curl -I https://<DOMAIN>` — Caddy'ye ulaşılıyor mu?
3. `make prod-logs service=caddy` — Caddy upstream'e (frontend/api) bağlanabiliyor mu?
4. `docker compose -f compose.production.yml --env-file .env.production ps` ile hangi container'ın çöktüğünü belirleyin, ilgili bölüme geçin.

## Caddy sertifika alamıyor

Olası nedenler ve kontroller:
- DNS domain'i doğru IP'ye işaret etmiyor: `dig +short <DOMAIN>`.
- 80/443 bir güvenlik duvarı tarafından engelleniyor: sunucu sağlayıcınızın
  firewall/security group ayarını kontrol edin.
- Let's Encrypt rate limit'ine takıldınız (çok fazla deneme): birkaç saat
  bekleyin, `deploy/caddy/Caddyfile.local`'daki gibi test amaçlı
  `tls internal` KULLANMAYIN (production domain'de gerçek sertifika gerekir).
- Loglar: `make prod-logs service=caddy` içinde ACME hata mesajını arayın.

## Backend (`api`) unhealthy

1. `make prod-logs service=api` — traceback var mı?
2. `docker compose -f compose.production.yml --env-file .env.production exec api python -c "import app.main"` — import hatası mı?
3. Postgres/Redis erişilebilir mi: `make prod-health` içinde `postgres`/`redis` `healthy` mi?
4. Eksik/yanlış env değişkeni: `docker compose config` ile interpolasyonu kontrol edin (secret basmaz).
5. Migration eksik olabilir: `make prod-migrate` çalıştırıp tekrar deneyin.

## Frontend unhealthy

1. `make prod-logs service=frontend`.
2. `NEXT_PUBLIC_API_URL` build-arg'ı yanlış olabilir — bu yalnız YENİDEN
   BUILD ile düzelir (`make prod-build`), runtime env DEĞİŞTİRMEK yeterli
   DEĞİLDİR (Next.js bunu build-time'da client bundle'a gömer).
3. Healthcheck `/login`'e bakar — backend'in kendisi çökmüşse bu
   etkilenmeyebilir (frontend statik render eder), ama API çağrıları
   tarayıcıda başarısız olur; kullanıcı raporlarını `api` bölümüyle
   çapraz kontrol edin.

## PostgreSQL unhealthy

1. `make prod-logs service=postgres`.
2. Disk dolu mu: `df -h` (host üzerinde, `postgres_data` volume'ünün
   bulunduğu dosya sistemi).
3. `pg_isready` healthcheck'i manuel çalıştırın:
   `docker compose -f compose.production.yml --env-file .env.production exec postgres pg_isready -U <POSTGRES_USER> -d <POSTGRES_DB>`.
4. **ASLA** `docker compose down -v` ile "sıfırlama" denemeyin — bu veri
   kaybına yol açar. Önce bu runbook'un ilgili adımlarını, gerekirse
   `BACKUP_AND_RESTORE.md`'deki restore prosedürünü izleyin.

## Redis unhealthy

1. `make prod-logs service=redis`.
2. `REDIS_PASSWORD` yanlış girilmiş olabilir (api/worker/beat farklı bir
   şifreyle bağlanmaya çalışıyor olabilir — `.env.production`'da tutarlı
   olduğunu doğrulayın).
3. Redis kalıcı iş verisi TUTMAZ (bkz. `BACKUP_AND_RESTORE.md` §2) —
   son çare olarak `redis_data` volume'ünü sıfırlamak veri kaybına yol
   AÇMAZ (yalnız aktif oturumlar/kuyruktaki görevler kaybolur, kullanıcılar
   yeniden giriş yapar).

## Bir çağrı QUEUED'da takılı kaldı / worker job'ı almıyor gibi görünüyor

1. `make queue-status` — `place_call` görevi `active`/`reserved` listesinde
   görünüyor mu? Görünmüyorsa worker kuyruğu (`calls`) tüketmiyor demektir.
2. `make prod-logs service=worker` — `celery inspect ping` healthcheck'i
   `unhealthy` mi (bkz. `make prod-health`)? Worker container'ı restart
   döngüsünde mi?
3. **Bilinen tasarım** (`PHASE_8_RESILIENCE_REPORT.md`): `place_call`
   Celery seviyesinde OTOMATİK RETRY yapmaz (`max_retries=0`) — bir dial
   denemesi transient bir hatayla başarısız olursa görev tek seferde
   FAILED'e döner; yeniden arama, kampanya sistemin kendi backoff
   zamanlamasına (`call_policy.py::compute_next_retry`) bırakılır, elle
   tetiklenen tekil çağrılar için otomatik yeniden deneme YOKTUR.
4. Worker gerçekten çökmüşse (OOM/crash) ve görev `task_acks_late=True`
   sayesinde yeniden teslim edildiyse: **mükerrer gerçek arama riski YOKTUR**
   — Redis tabanlı bir tek-seferlik işaret (`idempotency_seen`), ikinci
   teslimatın gerçek SIP dial'ı tekrar denemesini engeller ve çağrıyı
   `duplicate_dispatch_prevented` nedeniyle güvenli şekilde FAILED'e alır
   (bkz. `services/api/app/tasks/call_tasks.py`, test:
   `test_place_call_redelivery_after_successful_dial_prevents_duplicate_real_call`).
5. En kötü durumda (yukarıdakilerin hiçbiri temizlemediyse): watchdog
   emniyet süpürmesi (`watchdog_sweep`, her 60s, `MAX_CALL_DURATION_SECONDS
   + 600` saniyeden eski aktif/kuyruktaki çağrıları zorla FAILED'e alır)
   en fazla ~15 dakika içinde durumu kendiliğinden temizler.

## Voice-agent bağlantı kuramıyor

**Beklenen davranış** (gerçek LiveKit/OpenAI credential'ları yoksa veya
yanlışsa): `VOICE_AGENT_ENV=production` iken `agent/config.py`'nin
`_production_requires_secrets` doğrulayıcısı eksik ayarları AÇIKÇA
reddeder — container `configuration error: missing production settings:
...` ile **temiz bir şekilde exit(2)** olur, sonsuz/anlamsız bir crash
loop DEĞİL, Docker'ın standart `restart: unless-stopped` üstel geri
çekilmesiyle yeniden dener. Bu ampirik olarak doğrulandı (bkz.
`PRODUCTION_INFRA_REPORT.md` §14).

1. `make prod-logs service=voice-agent` — mesaj `configuration error: ...`
   ise: eksik/yanlış `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`/
   `OPENAI_API_KEY`/`INTERNAL_SERVICE_TOKEN` demektir — `.env.production`'ı
   düzeltip `docker compose up -d voice-agent` ile yeniden başlatın.
2. Credential'lar doğruysa ama hâlâ bağlanamıyorsa: LiveKit projesinin
   gerçekten erişilebilir olduğunu (`LIVEKIT_URL` doğru mu, ağ/firewall
   LiveKit'e giden trafiği engelliyor mu) kontrol edin — `voice-agent`
   yalnız `edge` ağındadır ve internet erişimi olmalıdır.
3. `INTERNAL_SERVICE_TOKEN` ile `api`'ye bağlanamıyorsa: aynı token'ın
   HEM `api` HEM `voice-agent` ortamında AYNI olduğunu doğrulayın (ikisi
   de `.env.production`'daki tek `INTERNAL_SERVICE_TOKEN`'dan gelir, ama
   yalnızca bu değişkeni elle override ettiyseniz tutarsızlık oluşabilir).

## Migration başarısız

1. `docker compose -f compose.production.yml --env-file .env.production run --rm migrate` çıktısını okuyun — Alembic hangi revizyonda başarısız oldu?
2. Postgres erişilebilir mi (bkz. "PostgreSQL unhealthy")?
3. Şema çakışması varsa (ör. elle yapılmış bir DB değişikliği): `alembic
   history`/`alembic current` ile mevcut durumu inceleyin, geri almadan
   önce **backup alın**.
4. ASLA migration'ı birden fazla `api`/`worker` replikasından eşzamanlı
   tetiklemeyin — `migrate` her zaman TEK, ayrı bir komuttur.

## Disk doluyor

1. `df -h` — hangi volume/dosya sistemi dolu?
2. Log boyutu sınırlıdır (`json-file`, servis başına en fazla 50 MB) —
   bu genelde asıl neden DEĞİLDİR.
3. `postgres_backups` volume'ü büyüyorsa: `BACKUP_RETENTION_DAYS`'i
   düşürün veya `make backup-verify-all` ile eski/bozuk dosyaları
   inceleyip elle temizleyin (yalnız checksum'lı, doğrulanmış dosyaları
   silin).
4. PostgreSQL'in kendi veri dizini büyüyorsa: `VACUUM`/retention
   politikalarını (`TRANSCRIPT_RETENTION_DAYS` — Celery beat'in
   `retention-cleanup` görevi bunu zaten periyodik uyguluyor) gözden
   geçirin.

## Backup başarısız

1. `journalctl -u ivac-postgres-backup.service -n 100` veya
   `make prod-logs service=backup` (manuel tetiklenen son çalıştırma için).
2. Yaygın nedenler: disk dolu (script bunu ÖNCEDEN algılayıp AÇIK hata
   verir), Postgres erişilemez, `PGPASSWORD` yanlış.
3. `make backup` ile manuel yeniden deneyin; hâlâ başarısızsa
   `scripts/backup/postgres-backup.sh`'i `bash -x` ile elle çalıştırıp
   hangi adımda durduğunu izleyin.

## Off-site upload başarısız

1. `RESTIC_REPOSITORY`/`RESTIC_PASSWORD`/`AWS_*` değişkenlerini kontrol
   edin (yalnız isim/varlık — değerleri loglamayın).
2. Ağ erişimi: `backup` servisi HEM `data` (postgres'e erişim) HEM `edge`
   (internet/S3 erişimi) ağındadır — `data` ağı `internal:true` olduğu için
   tek başına yeterli olmazdı, bu yüzden `backup` bilinçli olarak iki ağa da
   üye. İnternet erişimi sorunuysa host/bulut sağlayıcı güvenlik duvarını
   kontrol edin.
3. `restic unlock` gerekebilir (önceki bir çalışma yarıda kesildiyse):
   `docker compose run --rm --entrypoint restic backup unlock`.

## Restore gerekiyor

`BACKUP_AND_RESTORE.md` §10 "Production Restore Prosedürü"nü izleyin.
ASLA `--force` olmadan, ASLA checksum doğrulamadan restore ÇALIŞTIRMAYIN.

## Loglarda hassas veri şüphesi

1. Şüpheli log satırını izole edin, TERMİNALE/dokümana yapıştırmadan önce
   dikkatli olun.
2. Backend log redaction katmanları var (`app/core/logging.py` ve
   voice-agent'ın `agent/logging.py::RedactingFormatter`) — eğer bunlara
   rağmen sızıntı bulduysanız bu bir KOD hatasıdır, `CODEX_AUDIT_PHASE_4.md`/
   `CLAUDE_FIX_PHASE_4.md`'deki disiplinle (kök neden + test + düzeltme)
   ayrı bir oturumda ele alınmalıdır — bu runbook kapsamında YALNIZ mevcut
   log akışını durdurup (`docker compose stop <servis>`) etkiyi sınırlayın.
3. Sızan bir secret (token/parola) varsa: o secret'ı DERHAL rotate edin
   (`.env.production`'da değiştirip ilgili servisleri yeniden başlatın).

## Güvenli Rollback

`DEPLOYMENT.md` §13'ü izleyin. Özet: `git checkout <önceki-commit>` →
`make prod-build` → (şema geri gitmesi gerekiyorsa backup alıp dikkatli
`alembic downgrade`) → `up -d`. Volume'lara asla `-v` ile dokunmayın.
