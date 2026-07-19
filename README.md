# İşletme Vitrini AI Çağrı Merkezi

Yerel işletmelere (web sitesi olmayan/dijital görünürlüğü zayıf) yönelik, LiveKit + OpenAI Realtime tabanlı bir AI sesli satış/tanıtım çağrı merkezi. Sistem lead'leri (potansiyel müşteri) toplu içe aktarır, kampanya/manuel akışlarla giden (outbound) telefon araması başlatır, gerçek zamanlı bir konuşma motoruyla (OpenAI Realtime, LiveKit SIP üzerinden Netgsm trunk'ına) görüşmeyi yürütür, sonucu (ilgilendi/ilgilenmedi/demo talebi/geri arama vb.) yapılandırılmış olarak kaydeder ve bunu bir yönetim panelinden izlenebilir hale getirir.

## Mimari (özet)

```
Next.js panel  ──┐
                 ├─► Caddy (TLS/proxy) ──► FastAPI backend ──► PostgreSQL
Playwright E2E ──┘                              │                Redis (oturum, kilit, kuyruk, idempotency)
                                                 ├─► Celery worker/beat (arama dispatch, watchdog, kampanya tick)
                                                 └─► voice-agent (LiveKit Agent) ──► LiveKit SIP ──► Netgsm ──► gerçek telefon
                                                       │
                                                       └─► OpenAI Realtime (konuşma)
```

Detaylı bileşen sınırları, veri akışı ve çağrı yaşam döngüsü için: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Servisler

| Servis | Yol | Ne yapar |
|---|---|---|
| `apps/web` | Next.js 15 yönetim paneli | Lead/kampanya/çağrı/kullanıcı yönetimi, canlı arama izleme (SSE) |
| `services/api` | FastAPI backend | Auth/RBAC, lead/kampanya/çağrı CRUD, internal voice-agent contract API, Celery task tanımları |
| `services/voice-agent` | LiveKit Agent (Python) | Gerçek zamanlı konuşma runtime'ı — OpenAI Realtime + LiveKit SIP |
| `worker`/`beat` | Celery (aynı `services/api` image'ı, farklı komut) | Dial dispatch, watchdog, kampanya zamanlama, retention temizliği |
| `tests/e2e` | Playwright | Gerçek backend+DB'ye karşı uçtan uca testler (mock yok) |

## Yerel geliştirme

```bash
make setup              # pnpm install + uv sync (backend + voice-agent)
make infra-up           # Postgres + Redis (docker-compose.dev.yml)
cd services/api && uv run alembic upgrade head && uv run python -m app.seed
BOOTSTRAP_ADMIN_EMAIL=... BOOTSTRAP_ADMIN_PASSWORD=... uv run python -m app.bootstrap
make api                # ayrı terminal — uvicorn :8000
make worker              # ayrı terminal — celery worker
make beat                 # ayrı terminal — celery beat (opsiyonel, kampanya/watchdog için)
make web                 # ayrı terminal — Next.js dev :3000
```

`.env.example` dosyasını kopyalayıp doldurun (gerçek LiveKit/OpenAI/Netgsm credential'ları OLMADAN da backend/panel çalışır — yalnız gerçek arama denemesi `LIVE_CALLS_ENABLED=false` varsayılanıyla zaten engellidir).

## Test etme

```bash
make check          # backend: ruff + mypy + pytest
cd services/voice-agent && uv run ruff check agent tests && uv run mypy agent tests && uv run pytest
pnpm lint && pnpm typecheck && pnpm test    # frontend + root workspace
pnpm --filter @ivac/e2e test                # Playwright E2E (gerçek backend gerektirir, README'deki ön koşullar)
```

**Gerçek arama olmadan demo/test**: `LIVE_CALLS_ENABLED=false` (varsayılan) iken hiçbir çağrı dispatch edilmez. `TestTelephonyProvider` (`services/api/app/providers/telephony.py`) ve voice-agent'ın `Fake*` adaptörleri (`agent/session.py`, yalnız test kodunda) ağa hiç çıkmadan tüm iş mantığını (state machine, idempotency, watchdog, tool çağrıları) uçtan uca test eder — 300+ backend/voice-agent testi bunları kullanır.

## Production build ve deploy

```bash
make prod-config     # compose interpolasyon/şema doğrulaması (secret basmaz)
make prod-build      # tüm production image'ları derle
make prod-up         # stack'i başlat (migration ayrı, otomatik değil)
make prod-migrate    # tek seferlik migration
make doctor          # container durumu + /ready + backup durumu (tek komut)
```

Detaylı adım adım kurulum: **[docs/production/DEPLOYMENT.md](docs/production/DEPLOYMENT.md)**. Pilot öncesi/production öncesi kontrol listeleri: **[docs/GO_LIVE_CHECKLIST.md](docs/GO_LIVE_CHECKLIST.md)**, **[docs/PILOT_RUNBOOK.md](docs/PILOT_RUNBOOK.md)**.

## Env dosyaları

| Dosya | Amaç | Commit edilir mi |
|---|---|---|
| `.env.example`, `apps/web/.env.example` | Yerel geliştirme şablonu (gerçek değer yok) | ✅ |
| `.env.production.example` | Production değişken şablonu (gerçek değer yok) | ✅ |
| `.env.production` | Gerçek production secret'ları | ❌ (`.gitignore`) |
| `.env.e2e` (varsa) | Disposable Docker E2E testi için yerel override | ❌ (`.gitignore`, `.env.*` deseni) |

Değişken referansı (her biri: servis, zorunlu/opsiyonel, secret mi, örnek format, production uyarısı): **[docs/ENVIRONMENT_REFERENCE.md](docs/ENVIRONMENT_REFERENCE.md)**.

## Güvenlik sınırları (özet)

- Oturum: httpOnly + Secure(prod) + SameSite=Lax cookie, sunucu tarafında Redis'te (JWT değil). CSRF: double-submit + HMAC.
- RBAC: `owner`/`admin`/`sales_agent`/`viewer` — her mutasyon/hassas-okuma endpoint'i backend'de `require_permission` ile korunur (frontend gösterimi yalnız UX, güvenlik kontrolü değil).
- PII: telefon numaraları şifreli saklanır (`PII_ENCRYPTION_KEY`), panelde varsayılan olarak maskeli gösterilir, açma işlemi ayrı yetki + audit gerektirir + rate-limitlidir.
- İç servisler arası API (`/api/internal/*`) yalnız `INTERNAL_SERVICE_TOKEN` ile kimlik doğrulanır, Caddy dışarıdan bu path'i asla proxy'lemez.
- Log redaksiyonu: telefon/e-posta/Bearer-token/API-key desenleri hem backend hem voice-agent'ta hem düz mesajlarda hem exception traceback'lerinde temizlenir.

Tam güvenlik denetimi ve kapatılan bulgular: **[PHASE_9_SECURITY_REPORT.md](PHASE_9_SECURITY_REPORT.md)**, **[docs/production/SECURITY_CHECKLIST.md](docs/production/SECURITY_CHECKLIST.md)**.

## Diğer dokümanlar

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — bileşen sınırları, veri akışı, çağrı yaşam döngüsü
- [docs/ENVIRONMENT_REFERENCE.md](docs/ENVIRONMENT_REFERENCE.md) — tüm env değişkenleri
- [docs/PILOT_RUNBOOK.md](docs/PILOT_RUNBOOK.md) — ilk gerçek pilot çağrı prosedürü
- [docs/GO_LIVE_CHECKLIST.md](docs/GO_LIVE_CHECKLIST.md) — production öncesi teknik kontrol listesi
- [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) — sürümleme/deploy/rollback süreci
- [docs/INCIDENT_RESPONSE.md](docs/INCIDENT_RESPONSE.md) — olay müdahale prosedürleri
- [docs/production/DEPLOYMENT.md](docs/production/DEPLOYMENT.md), [BACKUP_AND_RESTORE.md](docs/production/BACKUP_AND_RESTORE.md), [OPERATIONS_RUNBOOK.md](docs/production/OPERATIONS_RUNBOOK.md), [SECURITY_CHECKLIST.md](docs/production/SECURITY_CHECKLIST.md) — Aşama 6'da yazılan production altyapı dokümanları
- [OPEN_OPERATIONAL_BLOCKERS.md](OPEN_OPERATIONAL_BLOCKERS.md) — gerçek production'a geçmeden önce kullanıcının yapması gereken dış işler
- [docs/internal-voice-agent-api.md](docs/internal-voice-agent-api.md), [docs/voice-agent-runtime.md](docs/voice-agent-runtime.md), [docs/frontend-management-panel.md](docs/frontend-management-panel.md) — bileşen-seviyesi tasarım notları
