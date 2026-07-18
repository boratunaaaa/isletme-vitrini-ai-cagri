# PROJECT_STATUS.md

## Proje Amacı

İşletme Vitrini için FastAPI backend, LiveKit tabanlı voice-agent, OpenAI Realtime görüşme runtime'ı ve kampanya/çağrı operasyon altyapısı kurmak.

## Mevcut Durum

- Backend ilk üç aşama tamamlandı: FastAPI app, Alembic, domain testleri ve internal voice-agent API contract çalışıyor.
- ~~Aşama 4 tamamlandı~~ **DÜZELTME (2026-07-18, `CLAUDE_AUDIT_PHASE_4.md`):** İlk "Aşama 4 tamamlandı" iddiası hatalıydı — iki KRİTİK bulgu (konuşma döngüsü yoktu, log traceback'i PII sızdırıyordu) `CLAUDE_FIX_PHASE_4.md`'de düzeltildi.
- **2. DÜZELTME (2026-07-18, `CODEX_AUDIT_PHASE_4_FIX.md`):** Bağımsız Codex denetimi bu düzeltmeyi büyük ölçüde doğruladı ("ÖNEMLİ DÜZELTMELER GEREKLİ") ama 3 YÜKSEK risk buldu: runtime `error` event'i terminal sayılmıyordu, completion retry kalıcı 401/403/422 hatalarını da tekrar deniyordu, SIP busy/no_answer/rejected backend call status'una hiç taşınmıyordu. Üçü de `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`'de düzeltildi. Voice-agent artık **107 testten geçiyor** (1. düzeltme sonrası 83'tü), coverage `%87`; backend **118 testten geçiyor** (111'di, 7 yeni SIP-mapping testi eklendi, mevcutlar bozulmadı).
- Harici OpenAI, LiveKit, Netgsm veya gerçek telefon çağrısı yapılmadı (hiçbir düzeltme oturumunda yapılmadı).

## Son Yapılanlar

- **2026-07-18 (2. düzeltme oturumu)** — `CODEX_AUDIT_PHASE_4_FIX.md`'nin 3 YÜKSEK bulgusu düzeltildi: (1) `termination.py::_on_error` artık gerçek SDK `recoverable` alanına bakıp yalnız KESİN fatal (`recoverable=False`) hataları terminal sayıyor; (2) `agent/api_client.py`'ye `InternalAPIPermanentError`/`InternalAPITransientError` sınıflandırması + 429 `Retry-After` desteği eklendi, `CompletionGuard` artık yalnız gerçek geçici hataları retry ediyor; (3) backend `/complete` endpoint'i yeni opsiyonel `sip_reason` alanını okuyup call'u doğru terminal statüye (`busy`/`no_answer`/`rejected`/`cancelled`) taşıyor ve **artık `campaign_service.handle_call_terminal`'i çağırarak** retry zamanlamasını gerçekten uyguluyor (önceden campaign_lead her zaman koşulsuz "completed" işaretleniyordu). Detay: `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`.
- **2026-07-18 (1. düzeltme oturumu)** — `CLAUDE_AUDIT_PHASE_4.md`'deki KRİTİK-1/KRİTİK-2 ve YÜKSEK-1..4 bulgularının tamamı `services/voice-agent/agent/**` içinde düzeltildi: yeni `agent/termination.py` (gerçek SDK `close`/`agent_state_changed` event'leriyle görüşme sonu bekleme), `job_handler.py`'de tam yeniden yazılan konuşma döngüsü + retry'lı `CompletionGuard` + `SessionEventBridge` (transcript/speech event aktarımı), `agent/logging.py`'de traceback'i de kapsayan `RedactingFormatter`, `agent/usage.py`'de gerçek `session.usage` okuma, `agent/errors.py`+`agent/sip.py`'de RFC 3261 SIP durum kodu ayrımı. Detay: `CLAUDE_FIX_PHASE_4.md`.
- `services/voice-agent` altında Python 3.11 `uv` projesi oluşturuldu.
- Resmi/kurulu SDK yüzeyi doğrulandı: `livekit-agents 1.5.17`, `livekit-plugins-openai 1.5.17`, `livekit-api 1.2.0`, `openai 2.46.0`.
- `docs/voice-agent-runtime.md`, `docs/internal-voice-agent-api.md`, `infrastructure/docker/voice-agent.Dockerfile` ve compose `voice` profili eklendi/güncellendi.
- `CLAUDE_PROGRESS_PHASE_4.md`, `CLAUDE_AUDIT_PHASE_4.md`, `CLAUDE_FIX_PHASE_4.md`, `CODEX_AUDIT_PHASE_4_FIX.md`, `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md` raporları oluşturuldu.

## Sıradaki En Doğru Adım

- Staging'e geçmeden önce: LiveKit URL/API key/secret, OpenAI API key, önceden oluşturulmuş SIP outbound trunk ID ve backend internal token hazırlanmalı.
- İlk staging testi gerçek müşteri numarasıyla değil, kontrollü test numarasıyla (`TEST_PHONE_ALLOWLIST`) yapılmalı.
- Bilinen kalan sınırlamalar (bkz. `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md` §20-21): `AgentSession(allow_interruptions=..., min_interruption_duration=...)` kwargs'ları SDK'da deprecated; `agent/main.py` CLI wrapper'ı hâlâ test edilmiyor (0% coverage); usage delivery hatasının completion reason'ı bozabilmesi (Codex ORTA-2, bu oturumun kapsamı dışında bilerek bırakıldı); end-call kapanış cümlesinin doğrudan `SpeechHandle` yerine `agent_state_changed`+grace penceresiyle beklenmesi (Codex ORTA-1).
- `~/AI_MEMORY/GLOBAL_STATUS.md` hâlâ eski Phase 4 bilgisini taşıyor — proje dışı dosya, bu oturumda değiştirilmedi, manuel güncelleme gerekiyor.

## Riskler / Dikkat Edilecekler

- Gerçek SIP/OpenAI/LiveKit runtime davranışı credential ve staging ortamı olmadan hâlâ doğrulanmadı (hiçbir düzeltme oturumunda yapılmadı — yasaktı).
- Telefon, token, API key ve transcript loglanmamalı; artık `logger.exception()`/traceback dahil test ediliyor (`tests/test_logging_redaction.py`, 8 test).
- Dosya silme, commit/push, deploy ve gerçek arama açık kullanıcı onayı olmadan yapılmamalı.
