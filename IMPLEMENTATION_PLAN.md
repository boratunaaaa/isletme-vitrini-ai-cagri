# IMPLEMENTATION_PLAN.md — İşletme Vitrini AI Çağrı Merkezi

Tarih: 2026-07-17 · Ortam: macOS 15.7 (Intel x86_64, 8 GB RAM) · Hedef: Üretime hazır uygulama

## 1. Doğrulanmış teknik varsayımlar

| Konu | Doğrulama | Sonuç |
|---|---|---|
| OpenAI Realtime modelleri | developers.openai.com + duyuru (2026-07-06) | `gpt-realtime-2.1` ve `gpt-realtime-2.1-mini` GA; fiyatlar spec ile birebir aynı (audio in $10/$32, out $20/$64 per 1M) |
| LiveKit outbound çağrı | docs.livekit.io/sip/outbound-calls | `CreateAgentDispatchRequest(agent_name, room, metadata)` → agent job içinde `CreateSIPParticipantRequest(sip_trunk_id, sip_call_to, room_name, participant_identity, wait_until_answered=True)`; hata: `api.SipCallError(sip_status_code, sip_status)` |
| Outbound trunk | docs.livekit.io/sip/trunk-outbound | `CreateSIPOutboundTrunkRequest(trunk=SIPOutboundTrunkInfo(name, address, numbers, auth_username, auth_password, transport))`; transport enum `SIP_TRANSPORT_UDP/TCP/TLS/AUTO` |
| Realtime plugin | docs.livekit.io/agents/integrations/realtime/openai | `from livekit.plugins import openai` → `openai.realtime.RealtimeModel(model, voice, temperature, turn_detection, modalities)`; `AgentSession(llm=...)` |

## 2. Mimari kararlar

1. **Sync SQLAlchemy 2 + psycopg3** her yerde (FastAPI sync endpoint'ler threadpool'da koşar; Celery zaten sync). Async yalnız SSE/Redis pub-sub ve LiveKit API çağrılarında. Gerekçe: tek ORM modeli, mypy/test basitliği, greenlet tuzağı yok.
2. **Oturum: opaque token + Redis session store** (httpOnly+Secure+SameSite=Lax cookie, CSRF double-submit, Argon2id). JWT yerine tercih gerekçesi: anlık iptal (revoke), daha küçük saldırı yüzeyi. `JWT_SECRET` CSRF HMAC'i ve dahili servis imzaları için kullanılır.
3. **Voice agent ↔ API iletişimi**: agent tüm tool etkilerini (`finalize_call_outcome`, `schedule_callback` …) API'nin `/internal/*` endpoint'leri üzerinden yapar (Bearer `INTERNAL_SERVICE_TOKEN`). Tek doğrulama+audit noktası; agent DB'ye doğrudan bağlanmaz.
4. **Görev kuyruğu: Celery + Redis** (worker + beat). Kampanya tick'i, retry, callback zamanlama, watchdog, retention temizliği beat üzerinden.
5. **Canlı panel: SSE** (`sse-starlette`) + Redis pub/sub. Voice agent olayı API'ye POST eder → API DB'ye yazar + kanala yayınlar → panel EventSource ile dinler.
6. **Provider mimarisi**: `ConversationEngineProvider` (voice-agent içinde: openai_realtime / local_pipeline stub / test), `TelephonyProvider` (api içinde: livekit_netgsm / test), `PlacesProvider` (google / imported), `NotificationProvider` (in-app / wa.me manuel). Domain katmanı SDK'lara bağımlı değil.
7. **PII**: telefonlar AES-256-GCM (`PII_ENCRYPTION_KEY`) ile şifreli, `phone_hash` = HMAC-SHA256(`PHONE_HASH_PEPPER`), `phone_last_four` maskeli gösterim için. Numara çözme yalnız owner/admin + audit log; loglarda redaksiyon filtresi.
8. **Celery worker kodu `services/api` paketinde** (`app/worker.py` + `app/tasks/`); `services/worker` yalnız Dockerfile/entrypoint taşır (aynı imaj, farklı komut). Gerekçe: tek şema+model kaynağı, çift paket senkron sorunu yok.
9. **Idempotency + kilit**: call başlatmada Redis `SET NX` lead kilidi + `calls.idempotency_key` unique + aktif çağrı için partial unique index (`lead_id WHERE status IN (aktif durumlar)`).
10. **8 GB Intel Mac kısıtı**: Colima 2 CPU/3 GB; lokalde yalnız Postgres+Redis konteyner, API/worker/web yerel süreç. LiveKit server/SIP lokalde varsayılan başlamaz (compose profili var, prod'da tam stack). Observability (Prometheus/Grafana) yalnız prod opsiyonel profile.
11. **Şema genişletmeleri** (spec "en az" dediği için eklendi): `calls.agent_prompt_version_id` + `calls.idempotency_key`, `call_usage.usage_source` (provider/estimated/mixed), `import_jobs` (import raporu), `call_quality_metrics` (bölüm 29), `lead_tag_map` (n-n), `INTERNAL_SERVICE_TOKEN` env.

## 3. Riskli varsayımlar / bilinçli sınırlar

- **LiveKit server + SIP çalışma zamanı doğrulaması bu Mac'te yapılamaz** (kaynak + gerçek SIP ucu gerekir). Kod ve config gerçek SDK'ya karşı yazılır, compose config doğrulanır; ilk gerçek çalışma VPS'te `docs/live-call-checklist.md` ile yapılır.
- **Netgsm SIP değerleri** (host/port/codec) env-tabanlı; Netgsm hesap panelindeki gerçek değerlerle kullanıcı dolduracak. Doküman: `docs/netgsm-sip-setup.md`.
- **Plugin `reasoning`/turn-detection parametre yüzeyi** sürüme göre değişebilir → kurulu paket imzasına göre güvenli kwargs filtresi (parametre uydurulmaz, desteklenmeyen ayar loglanıp atlanır).
- **Türkiye düzenlemesi (İYS/KVKK)**: soğuk aramada ticari elektronik ileti izni gerekebilir. Kod tarafında suppression + saat + limit korumaları var; hukuki uygunluk kullanıcı sorumluluğunda, `docs/live-call-checklist.md`'de açık uyarı.
- **Fiyat çelişkisi**: Canlı isletmevitrini.com paketleri 1.990/3.990/7.490 TL iken bu spec bilgi bankasına 5.000/10.000 TL + KDV seed istiyor. Spec'e uyuldu; panelden düzenlenebilir. Canlı kampanya öncesi kullanıcı teyidi şart.

## 4. Uygulama sırası

A1 ortam+plan → A2 monorepo → A3 DB+auth → A4 lead/kampanya → A5 voice AI → A6 SIP orkestrasyon → A7 panel → A8 test → A9 dokümantasyon → FINAL_REPORT.

## 5. Sürüm hedefleri

Node 26 (mevcut), pnpm 10, Next.js 15, React 19, Tailwind 4, TanStack Query 5, zod 3; Python 3.11 (uv-managed), FastAPI 0.115+, SQLAlchemy 2.0.3x, Pydantic 2.9+, Celery 5.5, livekit-agents 1.2+, livekit-api 1.x. Kesin sürümler lockfile'larda.
