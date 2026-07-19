# DEPLOYMENT.md — Production Kurulum Rehberi

Bu doküman `compose.production.yml` ile İşletme Vitrini AI Çağrı Merkezi'ni
gerçek bir sunucuda çalıştırmak için gereken TÜM adımları içerir. Mimari
gerekçeler için `PRODUCTION_INFRA_REPORT.md`'ye bakınız.

## 1. Sunucu Ön Koşulları

- Linux sunucu (systemd'li bir dağıtım önerilir — backup zamanlaması buna dayanır).
- Docker Engine ≥ 24 ve Docker Compose v2 (`docker compose version`).
- En az 2 vCPU / 4 GB RAM (tüm servisler + build için önerilen minimum).
- 80 ve 443 portları başka bir servis tarafından KULLANILMIYOR olmalı.
- DNS'te sunucunuzun IP'sine işaret eden bir domain (Caddy otomatik HTTPS için gerekli).

## 2. Docker/Compose Gereksinimleri

```bash
docker --version          # >= 24.x
docker compose version    # v2.x
```

Bu proje `docker compose` (v2, boşluklu) komutunu kullanır — eski `docker-compose`
(tire ile) komutu desteklenmez/test edilmedi.

## 3. Domain ve DNS Ayarı

1. Domain'inizin A/AAAA kaydını sunucunun public IP'sine yönlendirin.
2. DNS yayılımını doğrulayın: `dig +short panel.example.com`.
3. Caddy, `.env.production`'daki `DOMAIN` değeri için Let's Encrypt'ten
   otomatik sertifika alacaktır — bu adım TAMAMLANMADAN Caddy 80/443'ü
   dinlemeye başlasa bile HTTPS sertifikası alamaz (HTTP-01 challenge DNS'in
   doğru olmasını gerektirir).

## 4. `.env.production` Oluşturma

```bash
cp .env.production.example .env.production
```

Sonra HER `REPLACE_ME` değerini gerçek, güçlü, rastgele bir değerle
değiştirin:

```bash
openssl rand -base64 32   # JWT_SECRET, COOKIE_SECRET, PII_ENCRYPTION_KEY,
                           # PHONE_HASH_PEPPER, INTERNAL_SERVICE_TOKEN,
                           # POSTGRES_PASSWORD, REDIS_PASSWORD, RESTIC_PASSWORD
```

**Secret'ların repoya yazılmaması**: `.env.production` `.gitignore`'dadır
(`.env.*` deseni + `!.env.production.example` istisnası — bkz. kök
`.gitignore`). `git status` çalıştırıp bu dosyanın ASLA "değişiklik" olarak
görünmediğini doğrulayın. Bu dosyayı sunucuya `scp`/gizli bir secret
yöneticisiyle taşıyın — asla e-posta/Slack/commit mesajı içine yapıştırmayın.

`docker compose config` zorunlu değişkenleri (`${VAR:?...}` sözdizimi)
eksikse AÇIK bir hatayla durur — hangi değişkenin eksik olduğunu size söyler.

## 5. Image Build

```bash
make prod-build
# veya
docker compose -f compose.production.yml --env-file .env.production build
```

`frontend` image'ı `NEXT_PUBLIC_API_URL` build-arg'ını `.env.production`'daki
`API_URL`'den alır — bu değer YANLIŞSA frontend YENİDEN BUILD EDİLMEDEN
düzeltilemez (Next.js `NEXT_PUBLIC_*` değişkenlerini build-time'da client
bundle'a gömer). `API_URL`'i değiştirdiyseniz `make prod-build` ile
`frontend`'i yeniden derleyin.

**`API_URL`'e ASLA `/api` suffix'i eklemeyin** (yalnız `https://panel.example.com`
gibi bir origin) — frontend client'ı (`apps/web/lib/api/client.ts`) zaten her
istek path'ini `/api/...` ile başlatıyor; suffix eklenirse tüm istekler
`/api/api/...`'a gider ve Caddy'nin `/api/*` route'una hiç uymaz (panel
tamamen kullanılamaz hale gelir). Bu, `CODEX_AUDIT_PHASE_6.md` KRİTİK-1
bulgusuydu — ampirik olarak doğrulanıp düzeltildi.

## 6. Migration

```bash
make prod-migrate
# veya
docker compose -f compose.production.yml --env-file .env.production run --rm migrate
```

- Bu, `services/api/Dockerfile` imajını `alembic upgrade head` komutuyla
  **tek seferlik** çalıştırır (`profiles: ["tools"]` — asla `up -d` ile
  otomatik başlamaz).
- Birden fazla `api`/`worker` replikası varsa bile migration YALNIZ bu tek
  komutla, elle ve kontrollü şekilde tetiklenir — uygulama açılışında
  otomatik migration YOKTUR (yarış durumu riski yapısal olarak yok).
- Postgres `service_healthy` olana kadar bu komut bekler (`depends_on`
  health condition).

## 7. İlk Çalıştırma

```bash
make prod-up
# veya
docker compose -f compose.production.yml --env-file .env.production up -d
```

Bu, `migrate` ve `backup` HARİÇ tüm servisleri başlatır (`profiles: ["tools"]`
altındakiler varsayılan `up`'a dahil değildir).

## 8. Health Kontrolü

```bash
make prod-health
# veya
docker compose -f compose.production.yml --env-file .env.production ps
```

Beklenen: `postgres`, `redis`, `api`, `frontend`, `caddy`, `worker`, `beat`,
`voice-agent` → `healthy` (hepsinin gerçek healthcheck'i vardır — `worker`
`celery inspect ping`, `beat` kendi pidfile'ının canlılığını kontrol eder).

**`voice-agent` healthcheck'i — ne kanıtlar, ne kanıtlamaz:**

`voice-agent`'ın healthcheck'i **`--check-config` DEĞİLDİR** (eski bir
yaklaşımdı, `CODEX_REAUDIT_PHASE_6.md`'deki "healthcheck gerçekliği"
bulgusu üzerine kaldırıldı — yalnız env değişkenlerinin DOLU olduğunu
doğruluyordu, gerçek worker sürecinin başladığını veya LiveKit'e
bağlanabildiğini kanıtlamıyordu). Güncel uygulama
(`infrastructure/docker/voice-agent.Dockerfile`) LiveKit Agents SDK'sının
kendi worker HTTP sunucusuna (`GET http://127.0.0.1:8081/`) bir istek
atar — bu, SDK'nın kendi `AgentServer` health endpoint'idir.

Bu ayrımı netleştirmek önemlidir:

- **Docker `HEALTHCHECK` (liveness)**: yalnızca agent proses/SDK worker'ının
  ayakta olduğunu ve inference executor'ın çökmediğini, VEYA LiveKit'e
  bağlanma denemesinin kendi retry bütçesini (`max_retry=16`) TAMAMEN
  tüketmediğini doğrular. SDK bu iki durumdan herhangi birinde `200` döner —
  yani **hem "gerçekten bağlı" hem de "hâlâ bağlanmaya çalışıyor (retry
  içinde)" durumlarında container `healthy` görünür.** Yalnızca inference
  executor çöktüğünde veya 16 retry'nin tamamı tükendiğinde `503` (dolayısıyla
  `unhealthy`) olur.
- **Gerçek LiveKit bağlantısı ve çağrı kabul etme (readiness)**: `healthy`
  durumu TEK BAŞINA bunu KANITLAMAZ. Yanlış/eksik `LIVEKIT_URL` veya
  `LIVEKIT_API_KEY`/`SECRET` ile bile container, retry bütçesi tükenene kadar
  `healthy` görünmeye devam eder; arka planda gerçek bağlantı denemesi
  `401`/timeout gibi hatalarla başarısız olup exponential backoff ile
  YENİDEN DENER (crash-loop DEĞİL, ama bağlı da DEĞİL).

**Go-live öncesi bu yüzden `healthy` durumuna güvenmek YETERLİ DEĞİLDİR.**
Ek olarak şunlar yapılmalı:

1. `prod-logs service=voice-agent` ile logları izleyin — tekrarlayan
   `failed to connect to livekit, retrying...` satırları YERİNE gerçek bir
   bağlantı/job-ready logu görülmeli (bkz. `OPERATIONS_RUNBOOK.md`
   "Voice-agent bağlantı kuramıyor").
2. Gerçek LiveKit projesi + SIP trunk + OpenAI credential'ları girildikten
   sonra bağlantının fiilen kurulduğu loglardan doğrulanmalı.
3. `docs/PILOT_RUNBOOK.md`'deki kontrollü test-numarası dispatch/smoke
   testi çalıştırılmalı — yalnız bu, servisin GERÇEKTEN bir çağrıyı uçtan uca
   işleyebildiğini kanıtlar. `healthy` durumu tek başına gerçek bir SIP/LiveKit
   çağrısının yapılabildiğini KANITLAMAZ.

## 9. Caddy/TLS Kontrolü

```bash
curl -I https://panel.example.com
```

- `HTTP/2 200` (veya login'e yönlendirme) bekleyin.
- `Strict-Transport-Security` header'ının varlığını kontrol edin.
- İlk sertifika alımı birkaç dakika sürebilir; `make prod-logs service=caddy`
  ile ACME loglarını izleyin.

Yerel/DNS'siz doğrulama için `deploy/caddy/Caddyfile.local` kullanılabilir
(gerçek ACME denemez, `tls internal` ile self-signed sertifika üretir) —
bkz. o dosyanın başındaki yorum.

## 10. Log Görüntüleme

```bash
make prod-logs                      # tüm servisler
make prod-logs service=api          # yalnız api
docker compose -f compose.production.yml --env-file .env.production logs -f --tail=200 caddy
```

Loglar `json-file` sürücüsüyle döndürülür (`max-size: 10m`, `max-file: 5` —
her servis için en fazla 50 MB, disk sınırsız dolmaz).

## 11. Servis Restart

```bash
docker compose -f compose.production.yml --env-file .env.production restart api
```

## 12. Güncelleme (Yeni Sürüm Deploy)

```bash
git pull
make prod-build
make prod-migrate        # şema değişikliği varsa
docker compose -f compose.production.yml --env-file .env.production up -d
```

`up -d` yalnız değişen servisleri yeniden oluşturur (image hash değiştiyse).

## 13. Rollback

```bash
git checkout <önceki-commit>
make prod-build
docker compose -f compose.production.yml --env-file .env.production up -d
```

**Migration rollback dikkatli olun**: `alembic downgrade` şema değişikliğini
geri alır ama VERİ KAYBINA yol açabilir (ör. bir kolon silindiyse içindeki
veri geri gelmez). Şema geriye dönük uyumlu değilse önce güncel backup alın
(`make backup`), sonra `docker compose run --rm migrate alembic downgrade
<revizyon>`.

## 14. Durdurma

```bash
make prod-down
```

**Bu volume'ları SİLMEZ** — yalnız container'ları durdurur. `postgres_data`/
`redis_data`/`caddy_data`/`caddy_config`/`postgres_backups` named volume'ları
korunur.

## 15. Volume'ların Yanlışlıkla Silinmemesi

- `docker compose down -v` (veya `docker volume rm`) PostgreSQL verisini
  KALICI olarak siler. Bu proje bunu KOLAYLAŞTIRMAZ:
  - `make prod-down` volume SİLMEZ.
  - Volume silmek için AYRI, açıkça isimlendirilmiş `make
    prod-destroy-volumes force=yes` gerekir — `force=yes` olmadan REDDEDİLİR.
- `docker compose -f compose.production.yml --env-file .env.production down -v`
  komutunu ASLA rutin operasyonda kullanmayın.

## 16. İlk Backup Alma

```bash
make backup
make backup-status
```

Ayrıntı: `docs/production/BACKUP_AND_RESTORE.md`.

## 17. İlk Restore Tatbikatı

```bash
make restore-smoke-test
```

Bu, GERÇEK verinize DOKUNMADAN disposable bir veritabanında uçtan uca
backup+restore akışını test eder. **İlk production kurulumu, bu tatbikat en
az bir kez BAŞARIYLA çalıştırılmadan "tam hazır" SAYILMAZ** — yalnız
servislerin ayakta olması yeterli değildir; backup/restore mekanizmasının
GERÇEKTEN çalıştığı kanıtlanmalıdır.

## 18. Backup Zamanlamasını Kurma

```bash
sudo cp deploy/systemd/ivac-postgres-backup.service /etc/systemd/system/
sudo cp deploy/systemd/ivac-postgres-backup.timer /etc/systemd/system/
# .service dosyasındaki WorkingDirectory'i gerçek repo yoluna göre düzenleyin
sudo systemctl daemon-reload
sudo systemctl enable --now ivac-postgres-backup.timer
systemctl list-timers ivac-postgres-backup.timer
```

Ayrıntı: `docs/production/BACKUP_AND_RESTORE.md` §"Otomatik backup".
