# Mimari

## Bileşenler

| Bileşen | Teknoloji | Sorumluluk |
|---|---|---|
| `apps/web` | Next.js 15, React 19, TanStack Query/Table, Zod, Radix UI | Yönetim paneli: lead/kampanya/çağrı/kullanıcı yönetimi, canlı arama izleme |
| `services/api` | FastAPI, SQLAlchemy, Alembic, Celery (tanım) | REST API, auth/RBAC, domain mantığı, internal voice-agent contract |
| `services/voice-agent` | Python, `livekit-agents`, `livekit-plugins-openai` | Gerçek zamanlı konuşma runtime'ı — LiveKit job olarak çalışır |
| Celery `worker` | `services/api` image'ı, farklı komut | Dial dispatch (`place_call`), watchdog, kampanya işleri |
| Celery `beat` | `services/api` image'ı, farklı komut | Periyodik zamanlama (campaign-tick, watchdog-sweep, callback-sweep, retention-cleanup) |
| PostgreSQL | 16-alpine | Tek kalıcı doğruluk kaynağı (lead/çağrı/kullanıcı/audit) |
| Redis | 7-alpine | Oturum, CSRF, rate-limit, distributed lock, idempotency işaretleri, Celery broker/backend, SSE pub/sub |
| Caddy | 2-alpine | TLS terminasyonu, reverse proxy, tek dışa açık port |

## Docker network topolojisi (production)

```
edge (internal:false, internete/LiveKit-OpenAI-Netgsm'e çıkar)
  caddy (yalnız bu, host portlarını yayınlar: 80/443)
  frontend
  api
  worker
  voice-agent
  backup (yalnız off-site upload sırasında)

data (internal:true, internete kapalı)
  postgres
  redis
  api
  worker
  beat
  backup
```

`api`/`worker` HEM `data` HEM `edge` ağındadır (DB'ye erişmeli + LiveKit/harici API'lere çıkabilmeli). `beat` yalnız `data`'dadır (zamanlayıcı, dışarı çıkmaz). `voice-agent`/`frontend` yalnız `edge`'dedir (DB'ye doğrudan erişimi yok — backend'in internal API'si üzerinden konuşur). Yalnız `caddy` host port'u yayınlar; `api`/`frontend`/`voice-agent` container'ları dışarıdan doğrudan erişilemez.

## Caddy routing

- `/api/internal/*` → **her zaman 403** (Caddy seviyesinde, backend'e hiç ulaşmaz) — yalnız `voice-agent`→`api` arası, container-içi ağdan, `INTERNAL_SERVICE_TOKEN` ile erişilir.
- `/api/*` → `api:8000`
- `/health`, `/ready` → `api:8000`
- geri kalan her şey → `frontend:3000`

Access log'da `Authorization`/`Cookie` header'ları ve `next`/`token`/`code`/`email`/`phone` query parametreleri redakte edilir.

## Çağrı yaşam döngüsü

```
1. Panel/kampanya → POST /api/calls (idempotency_key opsiyonel)
2. orchestrator.initiate_call:
   - politika kapıları (LIVE_CALLS_ENABLED, çalışma saatleri [Pazar hariç], günlük/eşzamanlı limit, suppression listesi)
   - Redis lock (lead başına tek aktif çağrı, DB unique index ile de garanti)
   - Call satırı oluşturulur (status=QUEUED), Celery'ye place_call enqueue edilir
3. Worker: place_call
   - Redis idempotency işareti (mükerrer teslimatta gerçek dial'ın TEKRAR denenmesini engeller)
   - LiveKit Agent Dispatch oluşturulur (status=PREPARING→DIALING)
   - Hata: TelephonyError → status=FAILED, fallback outcome, kampanya/lead güncellenir
4. voice-agent job'ı SIP participant'ı davet eder (LiveKit resmi deseni)
5. voice-agent → api internal contract:
   - bootstrap (lead/kampanya/prompt bilgisi, telefon YALNIZ bu cevapta)
   - lifecycle event'leri (answered, tool çağrıları, transcript turn'leri, usage)
   - finalize-call-outcome (idempotent, DB'ye tek kaynak olarak yazılır)
6. watchdog_check (per-call, max_duration+180s sonra) + watchdog_sweep (60s periyodik emniyet)
   stuck çağrıları zorla FAILED'e alır
7. Frontend: SSE (/api/live/events) → React Query invalidation → gerçek REST fetch (SSE payload asla tek doğruluk kaynağı değil)
```

Detaylı dayanıklılık garantileri (worker crash/redelivery, duplicate-dispatch önleme, timeout matrisi): [PHASE_8_RESILIENCE_REPORT.md](../PHASE_8_RESILIENCE_REPORT.md).

## Voice-agent ↔ API sözleşmesi

`services/voice-agent` hiçbir zaman PostgreSQL'e doğrudan bağlanmaz — tüm durum `services/api`'nin `/api/internal/v1/*` uç noktaları üzerinden, `INTERNAL_SERVICE_TOKEN` bearer auth'uyla akar. Her mutasyon `external_id` (tool_call_id/event_id) ile idempotent'tir — aynı ID + aynı payload tekrar gelirse önbellek sonucu döner, aynı ID + farklı payload gelirse `409 DUPLICATE_EVENT_CONFLICT`. Tam sözleşme: [docs/internal-voice-agent-api.md](internal-voice-agent-api.md).

## Backup/restore

`backup` servisi hem `data` (Postgres'e erişim) hem `edge` (off-site S3/restic upload) ağındadır — tek servis, iki ağa bilinçli üye. Zamanlama systemd timer ile (Docker'ın kendi cron'u değil). Detay: [docs/production/BACKUP_AND_RESTORE.md](production/BACKUP_AND_RESTORE.md).

## Gözlemlenebilirlik

Yapılandırılmış JSON loglar (`request_id`/`call_id` korelasyonu, otomatik PII/secret redaksiyonu), `/health` + `/ready` (DB+Redis alt kontrolleri), `make doctor`/`ready-check`/`queue-status`. Detay: [PHASE_10_OPERATIONS_REPORT.md](../PHASE_10_OPERATIONS_REPORT.md).
