# Environment Değişken Referansı

**Hiçbir gerçek değer bu dosyada yer almaz** — yalnız isim, servis, zorunlu/opsiyonel, secret olup olmadığı, örnek FORMAT ve production uyarısı. Gerçek değerler yalnız `.env.production` içinde (gitignored) tutulur.

## Backend (`services/api`, `worker`, `beat`)

### Uygulama / ağ

| Değişken | Zorunlu | Secret | Örnek format | Varsayılan | Production notu |
|---|---|---|---|---|---|
| `APP_ENV` | ✅ (prod'da) | ❌ | `production` | `development` | `production` iken tüm secret validasyonları aktif olur |
| `APP_NAME` | ❌ | ❌ | `isletme-vitrini-ai-cagri` | aynı | — |
| `APP_URL` | ✅ (prod'da) | ❌ | `https://panel.example.com` | `http://localhost:3000` | trailing slash OLMADAN |
| `API_URL` | ✅ (prod'da) | ❌ | `https://panel.example.com` | `http://localhost:8000` | frontend build-time'da `NEXT_PUBLIC_API_URL`'e gömülür — DEĞİŞTİRMEK yeniden build gerektirir |
| `APP_TIMEZONE` | ❌ | ❌ | `Europe/Istanbul` | aynı | çalışma saatleri/backup zamanlaması buna göre |
| `CORS_ORIGINS` | ✅ (prod'da) | ❌ | `https://panel.example.com` | `http://localhost:3000` | **asla `*` olmamalı** |
| `TRUSTED_HOSTS` | ✅ (prod'da) | ❌ | `panel.example.com` | `localhost,127.0.0.1` | virgülle çoklu host |

### Veritabanı / Redis

| Değişken | Zorunlu | Secret | Örnek format | Varsayılan | Production notu |
|---|---|---|---|---|---|
| `DATABASE_URL` | ✅ | kısmen (parola içerir) | `postgresql+psycopg://user:pass@host:5432/db` | yerel Postgres | production PostgreSQL olmalı (SQLite reddedilir) |
| `DATABASE_URL_TEST` | ❌ (yalnız test) | kısmen | aynı format | yerel test DB | yalnız pytest kullanır |
| `REDIS_URL` | ✅ | kısmen (parola içerir) | `redis://:pass@host:6379/0` | yerel Redis | — |
| `DB_STATEMENT_TIMEOUT_MS` | ❌ | ❌ | `30000` | `30000` | 1000-300000 aralığı |

### Secret'lar (production'da fail-fast doğrulanır: min 20 karakter, placeholder marker'lar reddedilir)

| Değişken | Zorunlu | Örnek format | Notu |
|---|---|---|---|
| `JWT_SECRET` | ✅ | 40+ karakter rastgele string | CSRF HMAC + JWT imzalama |
| `COOKIE_SECRET` | ✅ | 40+ karakter rastgele string | — |
| `PII_ENCRYPTION_KEY` | ✅ | 40+ karakter rastgele string | telefon şifreleme (Fernet) |
| `PHONE_HASH_PEPPER` | ✅ | 40+ karakter rastgele string | telefon hash'leme (dedup için) |
| `INTERNAL_SERVICE_TOKEN` | ✅ | 40+ karakter rastgele string | voice-agent↔api auth — **her iki serviste de AYNI olmalı** |
| `INTERNAL_SERVICE_TOKEN_PREVIOUS` | ❌ | aynı format | token rotasyonu sırasında geçiş için (opsiyonel) |
| `BOOTSTRAP_ADMIN_EMAIL` | ❌ (yalnız bootstrap) | `admin@example.com` | yalnız ilk kurulumda `python -m app.bootstrap` çalışırken kullanılır |
| `BOOTSTRAP_ADMIN_PASSWORD` | ❌ (yalnız bootstrap) | 10+ karakter | aynı |

### LiveKit / Netgsm / OpenAI (gerçek arama için ZORUNLU)

| Değişken | Zorunlu | Secret | Örnek format | Notu |
|---|---|---|---|---|
| `LIVEKIT_URL` | gerçek arama için ✅ | ❌ | `wss://your-project.livekit.cloud` | `ws://`/`wss://` ile başlamalı |
| `LIVEKIT_API_KEY` | gerçek arama için ✅ | ✅ | LiveKit console'dan | — |
| `LIVEKIT_API_SECRET` | gerçek arama için ✅ | ✅ | LiveKit console'dan | — |
| `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` | gerçek arama için ✅ | ❌ | `ST_xxxxxxxx` | önceden LiveKit'te oluşturulmuş SIP trunk |
| `LIVEKIT_AGENT_NAME` | ❌ | ❌ | `ivac-outbound-agent` | explicit dispatch adı |
| `NETGSM_SIP_HOST/PORT/USERNAME/PASSWORD/OUTBOUND_NUMBER/TRANSPORT/CODEC_PREFERENCES` | gerçek arama için ✅ | (USERNAME/PASSWORD ✅) | — | Netgsm hesap bilgileri, LiveKit SIP trunk konfigürasyonuna girilir (bu repo'da doğrudan kullanılmaz, referans amaçlı) |
| `OPENAI_API_KEY` | gerçek arama için ✅ | ✅ | `sk-...` | — |
| `OPENAI_REALTIME_DEFAULT_MODEL/PREMIUM_MODEL/DEFAULT_VOICE/REASONING_EFFORT` | ❌ | ❌ | — | izin verilen değer listesi kodda sabit (`ALLOWED_MODELS`/`ALLOWED_VOICES`) |

### İş kuralları / özellik bayrakları

| Değişken | Varsayılan | Notu |
|---|---|---|
| `LIVE_CALLS_ENABLED` | `false` | **`false` iken hiçbir gerçek arama dispatch edilmez** — en önemli güvenlik anahtarı |
| `CAMPAIGNS_ENABLED` | `false` | — |
| `TEST_PHONE_ALLOWLIST` | boş | yalnız `is_production=false` iken uygulanır (dev/staging'de yanlışlıkla gerçek numara aranmasını önler) |
| `MAX_CONCURRENT_CALLS` | `1` | production'da gerçekçi bir değere yükseltilmeli |
| `MAX_DAILY_CALLS` | `10` | — |
| `DEFAULT_CALL_START_HOUR`/`END_HOUR` | `10`/`17` | Pazar günleri kod seviyesinde HER ZAMAN engellidir (env ile bypass edilemez) |
| `MAX_CALL_DURATION_SECONDS` | `300` | — |
| `DEFAULT_MAX_RETRY_COUNT`/`RETRY_DELAY_MINUTES` | `2`/`120` | kampanya seviyesi retry |
| `CALL_RECORDING_ENABLED` | `false` | — |
| `TRANSCRIPT_STORAGE_ENABLED`/`RETENTION_DAYS` | `true`/`30` | — |
| `AUDIO_RETENTION_DAYS` | `0` (saklanmaz) | — |
| `HUMAN_TRANSFER_ENABLED`/`NUMBER` | `false`/boş | — |
| `GOOGLE_PLACES_API_KEY`/`ENABLE_GOOGLE_PLACES` | boş/`false` | secret, opsiyonel |
| `WORKER_CONCURRENCY` | `2` | compose.production.yml build-arg |

### Operasyon

| Değişken | Varsayılan | Notu |
|---|---|---|
| `LOG_LEVEL` | `INFO` | — |
| `SENTRY_DSN` | boş | opsiyonel, bu repo'da entegrasyon şu an yok (yalnız değişken tanımlı) |
| `SESSION_IDLE_SECONDS`/`ABSOLUTE_SECONDS` | `43200`/`604800` | 12 saat / 7 gün |
| `POSTGRES_MEMORY_LIMIT`/`REDIS_MEMORY_LIMIT`/`API_MEMORY_LIMIT`/`WORKER_MEMORY_LIMIT`/`BEAT_MEMORY_LIMIT`/`VOICE_AGENT_MEMORY_LIMIT`/`FRONTEND_MEMORY_LIMIT` | compose.production.yml'de belgeli | Docker container bellek limitleri |

## Voice-agent (`services/voice-agent`)

| Değişken | Zorunlu (production) | Secret | Notu |
|---|---|---|---|
| `VOICE_AGENT_ENV` | ✅ | ❌ | `production` iken tüm secret'lar fail-fast doğrulanır |
| `INTERNAL_API_BASE_URL` | ✅ | ❌ | backend'in container-içi adresi (`http://api:8000`) |
| `INTERNAL_SERVICE_TOKEN` | ✅ | ✅ | backend ile AYNI değer |
| `LIVEKIT_URL`/`LIVEKIT_API_KEY`/`LIVEKIT_API_SECRET`/`LIVEKIT_SIP_OUTBOUND_TRUNK_ID` | ✅ | (KEY/SECRET ✅) | backend ile AYNI |
| `OPENAI_API_KEY` | ✅ | ✅ | backend'den bağımsız, ayrıca burada da tanımlı |
| `HTTP_TIMEOUT_SECONDS`/`HTTP_MAX_RETRIES`/`HTTP_MAX_RETRY_AFTER_SECONDS` | ❌ | ❌ | internal API çağrıları için |
| `EVENT_QUEUE_MAX_SIZE`/`TRANSCRIPT_QUEUE_MAX_SIZE` | ❌ | ❌ | — |
| `GRACEFUL_SHUTDOWN_SECONDS` | ❌ | ❌ | SIGTERM sonrası temizlik süresi (SDK `shutdown_process_timeout`'a bağlı) |
| `SIP_PARTICIPANT_TIMEOUT_SECONDS`/`REALTIME_STARTUP_TIMEOUT_SECONDS`/`SILENCE_WATCHDOG_SECONDS`/`END_CALL_GRACE_SECONDS` | ❌ | ❌ | — |

## Frontend (`apps/web`)

| Değişken | Secret | Notu |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | ❌ (build-time'da bundle'a gömülür, secret DEĞİLDİR) | **Değiştirmek yeniden `docker build` gerektirir** — runtime env değişikliği yeterli değildir (Next.js standalone build'i statik olarak gömer) |

## Backup (`scripts/backup/*.sh`)

| Değişken | Zorunlu | Secret | Notu |
|---|---|---|---|
| `POSTGRES_USER`/`PASSWORD`/`DB` | ✅ | (PASSWORD ✅) | `PGPASSWORD` env ile libpq'ya geçer, argv'ye YAZILMAZ |
| `BACKUP_RETENTION_DAYS` | ❌ | ❌ | local backup temizlik politikası |
| `BACKUP_REMOTE_ENABLED` | ❌ (varsayılan `false`) | ❌ | `true` ise restic off-site upload dener |
| `RESTIC_REPOSITORY`/`RESTIC_PASSWORD` | off-site için ✅ | (PASSWORD ✅) | `.env.production`'dan AYRI, ayrı bir secret store'da tutulması önerilir |
| `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` | S3 backend için ✅ | ✅✅ | restic S3 kullanıyorsa |
| `RESTIC_TIMEOUT_SECONDS` | ❌ | ❌ | `0` = timeout devre dışı DEĞİL, "hemen fail" (bkz. `PHASE_8`/Aşama 6 bulgusu) — üretimde makul bir pozitif değer kullanın |

## Genel kural

- Hiçbir env değeri (yalnız İSİM değil) rapora, log'a, commit mesajına veya bu dosyaya YAZILMAZ.
- `.env.production` her zaman `.gitignore`'dadır (`git check-ignore -v .env.production` ile doğrulanabilir).
- Yeni bir env değişkeni eklerken: `.env.production.example`'a İSİM+açıklama+placeholder ekleyin, gerçek değeri asla commit etmeyin, bu tabloyu güncelleyin.
