# SECURITY_CHECKLIST.md

Production deploy öncesi ve periyodik denetimlerde kullanılacak kontrol
listesi. Her madde gerçek dosya/komutla doğrulanabilir.

- [ ] **Yalnız 80/443 public.**
  ```bash
  docker compose -f compose.production.yml --env-file .env.production config | grep -A3 "ports:"
  ```
  Yalnız `caddy` servisi altında `80`, `443` (tcp), `443` (udp) görünmeli.

- [ ] **DB/Redis public değil.**
  ```bash
  docker compose -f compose.production.yml --env-file .env.production config --services
  ```
  `postgres`/`redis` tanımlarında `ports:` anahtarı YOK; yalnız `data` ağındalar (`internal: true`).

- [ ] **Default parola yok.** `.env.production`'da `POSTGRES_PASSWORD`,
  `REDIS_PASSWORD`, `JWT_SECRET`, `COOKIE_SECRET`, `PII_ENCRYPTION_KEY`,
  `PHONE_HASH_PEPPER`, `INTERNAL_SERVICE_TOKEN`, `RESTIC_PASSWORD`,
  `BOOTSTRAP_ADMIN_PASSWORD` hiçbiri `.env.production.example`'daki
  `REPLACE_ME`/örnek değerle AYNI olmamalı. `app/config.py::validate_runtime()`
  zaten production'da eksik secret'larla başlamayı REDDEDER (fail-fast) —
  ama "dolu ama zayıf" bir değer bu kontrolü geçebilir, elle doğrulayın.

- [ ] **Secret git geçmişinde yok.**
  ```bash
  git log --all -p -- .env.production 2>&1 | head -5   # boş olmalı (dosya hiç commit edilmemiş)
  git grep -n "REPLACE_ME\|BEGIN.*PRIVATE KEY" $(git rev-list --all) 2>/dev/null | head
  ```

- [ ] **Production debug kapalı.** `APP_ENV=production` iken FastAPI
  `debug` modu kullanılmıyor (kod içinde `debug=True` hiçbir yerde
  ayarlanmıyor — `app/main.py::create_app()` bunu hiç set etmez, FastAPI
  varsayılanı `False`'tur). `/docs`/`/redoc`/`/openapi.json` FastAPI
  varsayılan olarak AÇIKTIR — production'da bunları kapatmak isterseniz
  `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)` eklemek KÜÇÜK
  bir kod değişikliği gerektirir; bu oturumda YAPILMADI, bilinçli bir
  sonraki-adım olarak burada işaretleniyor (bkz. `PRODUCTION_INFRA_REPORT.md`
  §18 "Bilinen sınırlamalar").

- [ ] **CORS allowlist doğru.** `.env.production`'da `CORS_ORIGINS` YALNIZ
  gerçek frontend domain'ini (`https://panel.example.com`) içeriyor,
  `*` veya `http://localhost:3000` İÇERMİYOR.

- [ ] **Trusted hosts doğru.** `TRUSTED_HOSTS` yalnız gerçek domain(ler)i
  içeriyor.

- [ ] **Cookie güvenlik ayarları doğru.** `app/core/security.py`'de
  `SESSION_COOKIE`/`CSRF_COOKIE` `httponly=True` (session) ve
  `secure=settings.is_production` (`APP_ENV=production` iken otomatik
  `True`) ile ayarlanıyor — kod okunarak doğrulandı, bu oturumda
  DEĞİŞTİRİLMEDİ. `APP_ENV=production` olduğunu doğrulayın (aksi halde
  `secure=False` olur).

- [ ] **HTTPS zorunlu.** Caddy `{$DOMAIN}` bloğu otomatik HTTP→HTTPS
  yönlendirmesi yapar (Caddy'nin varsayılan davranışı); `curl -I
  http://panel.example.com` bir `308`/`301` ile `https://`'e yönlendirmeli.

- [ ] **Proxy header güveni kontrollü.** `api` yalnız `edge` ağından (yani
  yalnız `caddy`'den) erişilebilir olduğu için `uvicorn --forwarded-allow-ips=*`
  KULLANILDI (bkz. `services/api/Dockerfile`) — bu güvenlidir ÇÜNKÜ `api`
  container'ı public'ten hiçbir şekilde doğrudan erişilemez (`data`+`edge`
  ağlarında, `ports:` YOK). Caddy da kendi `header_up X-Forwarded-*`
  direktifleriyle doğru değerleri iletir.

- [ ] **Caddy admin dışarı kapalı.** Caddy admin API varsayılan olarak
  yalnız `localhost:2019`'da dinler; `compose.production.yml`'de bu port
  için `ports:` tanımı YOK — yalnız container-içi healthcheck kullanır.

- [ ] **Image'lar root olmayan kullanıcıyla çalışıyor.**
  ```bash
  docker compose -f compose.production.yml --env-file .env.production run --rm api whoami   # ivac
  docker compose -f compose.production.yml --env-file .env.production run --rm frontend whoami  # ivac (Dockerfile'da tanımlı)
  docker compose -f compose.production.yml --env-file .env.production run --rm voice-agent whoami  # voiceagent
  ```

- [ ] **Gereksiz Linux capability yok.** Tüm uygulama servislerinde
  `cap_drop: [ALL]` + `security_opt: ["no-new-privileges:true"]`. Yalnız
  `caddy` 80/443'e bind edebilmek için `cap_add: [NET_BIND_SERVICE]` alır
  (minimum gerekli istisna, gerekçesi `PRODUCTION_INFRA_REPORT.md` §6'da).

- [ ] **Loglarda token/telefon/e-posta/şifre yok.** Backend
  (`app/core/logging.py`, `app/core/audit.py::write_audit` — `phone`/
  `password`/`token`/`secret`/`api_key`/`authorization` anahtarlarını
  filtreler) ve voice-agent (`agent/logging.py::RedactingFormatter`,
  `agent/redaction.py`) redaction katmanları bu oturumda DEĞİŞTİRİLMEDİ —
  önceki fazlarda (`CLAUDE_FIX_PHASE_4.md`) canlı repro ile doğrulanmıştı.
  Backup script'leri (`scripts/backup/*.sh`) `PGPASSWORD`'ü/connection
  string'i HİÇBİR log satırına yazmaz (yalnız dosya adı/checksum/boyut
  loglanır — kod okunarak doğrulandı).

- [ ] **Backup şifreli ve off-site.** `BACKUP_REMOTE_ENABLED=true` VE
  `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` gerçek değerlerle dolu mu?
  Doldurulmadıysa bu KRİTİK bir operasyonel eksik olarak işaretlenmelidir
  (bkz. `BACKUP_AND_RESTORE.md` §3).

- [ ] **Restore testi yapılmış.** `make restore-smoke-test` en az bir kez
  BAŞARIYLA çalıştırılmış mı? (`PRODUCTION_INFRA_REPORT.md` §16'da bu
  oturumun sonucu raporlanmıştır.)

- [ ] **Backup anahtarı ayrı güvenli yerde.** `RESTIC_PASSWORD` ve
  `PII_ENCRYPTION_KEY`/`PHONE_HASH_PEPPER`, `.env.production`'ın dışında
  AYRICA (ör. şirket parola yöneticisinde) saklanıyor mu? (Bkz.
  `BACKUP_AND_RESTORE.md` §11.)

- [ ] **Production database volume'u yanlışlıkla silinmeye karşı
  belgelenmiş.** `make prod-down` volume SİLMEZ; volume silme yalnız
  `make prod-destroy-volumes force=yes` ile AÇIKÇA mümkündür (bkz.
  `DEPLOYMENT.md` §15, `Makefile`).
