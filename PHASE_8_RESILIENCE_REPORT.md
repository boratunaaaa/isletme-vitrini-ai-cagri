# Aşama 8 — Dayanıklılık ve Hata Yönetimi

Tarih: 2026-07-19
Kapsam: Aşama 7 commit (`b38734e`) sonrası; LiveKit, OpenAI Realtime, Netgsm/SIP, PostgreSQL, Redis, Celery worker/beat, Caddy ve backup/restic yollarının hata/dayanıklılık denetimi. Gerçek dış bağlantı KURULMADI; yalnız mevcut sahte (`TestTelephonyProvider`, `FakeRealtimeSessionAdapter` vb.) adaptörler ve statik kod okuması kullanıldı.

## 1. Yöntem

17 senaryo (bağlantı hatası, timeout, 401/403, 429, 5xx, orta-görüşme kopması, worker crash, Redis/Postgres geçici kesinti, mükerrer job teslimatı, mükerrer çağrı isteği, kullanıcı/karşı taraf kapatma, max süre watchdog, tool çağrı hatası, audio pipeline kapanışı, crash-loop koruması, hata mesajı/redaksiyon) read-only bir ajanla tek tek dosya+satır bazında değerlendirildi. Sonrasında her GAP bizzat okunup doğrulandı ve minimal kapsamda düzeltildi.

## 2. Bulgu Özeti

| # | Bulgu | Ciddiyet | Durum |
|---|---|---|---|
| 1 | `app/tasks/call_tasks.py` (place_call/watchdog/hangup) hiç test edilmiyordu | Orta (görünürlük) | **Kapatıldı** — 7 yeni entegrasyon testi |
| 2 | `place_call` redelivery'de gerçek SIP dial'ı İKİNCİ kez deneyebilirdi (worker crash senaryosu) | **Yüksek** (mükerrer gerçek arama riski) | **Kapatıldı** — Redis idempotency guard + regresyon testi |
| 3 | `redis_lock()` Redis bağlantı hatasını yakalamıyordu → opak 500 | Orta | **Kapatıldı** — `LockBackendUnavailable` + 503 mapping + testler |
| 4 | `GRACEFUL_SHUTDOWN_SECONDS` hiçbir yere bağlı değildi; Docker `stop_grace_period` yoktu (varsayılan 10s SIGKILL) | Orta (operasyonel) | **Kapatıldı** — SDK `shutdown_process_timeout`'a bağlandı + compose `stop_grace_period` |
| 5 | DB sorguları için statement/connect timeout yoktu | Orta | **Kapatıldı** — `DB_STATEMENT_TIMEOUT_MS` (varsayılan 30s) |
| 6 | `services/api` log redaksiyonu `Authorization: Bearer <token>` içindeki asıl token'ı KAÇIRIYORDU; e-posta/OpenAI key hiç yakalanmıyordu | **Yüksek** (secret log sızıntısı) | **Kapatıldı** — voice-agent'ın kanıtlanmış desenleriyle hizalandı + 6 yeni test |
| 7 | `LiveKitRealtimeSessionAdapter.start()` (gerçek OpenAI bağlantı/timeout yolu) hiç test edilmiyordu | Orta (görünürlük) | **Kapatıldı** — 2 yeni test |
| 8 | `classify_sip_status`'ın trunk/auth/redirect/unknown dalları hiç test edilmiyordu | Düşük-Orta (görünürlük) | **Kapatıldı** — yeni `test_errors.py` (17 parametrized durum) |
| 9 | `ToolExecutor.execute()`'da `TOOL_CALL_STARTED` emit'i try/except DIŞINDAYDI | Düşük-Orta | **Kapatıldı** — emit try içine alındı + 2 yeni test |

Kritik/yüksek seviyede **açık kalan** bulgu yok. Bulgu #2 ve #6, ciddiyetleri nedeniyle bu turun en önemli düzeltmeleriydi.

## 3. Bulgu Detayları ve Düzeltmeler

### #2 — Mükerrer gerçek arama riski (EN KRİTİK)

`task_acks_late=True` + `worker_prefetch_multiplier=1` altında, worker gerçek SIP dial isteğini LiveKit'e gönderdikten SONRA ama `place_call`'ın kendi `session_scope()` transaction'ı commit edilmeden ÖNCE çökerse (OOM/SIGKILL), Celery görevi hâlâ-QUEUED bir DB satırıyla YENİDEN teslim eder — bu da `create_outbound_call`'ın ikinci kez çağrılıp gerçek bir müşteriyi mükerrer aramasına yol açabilirdi.

**Düzeltme** (`services/api/app/tasks/call_tasks.py`): dial denemesinden hemen önce mevcut `idempotency_seen()` yardımcı fonksiyonu (`app/core/locks.py`, zaten vardı, yeni bir soyutlama eklenmedi) ile Redis'te DB transaction'ından BAĞIMSIZ bir tek-seferlik işaret bırakılıyor. İkinci teslimat bu işareti görürse gerçek dial'ı asla tekrar denemeden çağrıyı `duplicate_dispatch_prevented` nedeniyle FAILED'e alıyor.

**Regresyon testi** (`tests/integration/test_call_tasks.py::test_place_call_redelivery_after_successful_dial_prevents_duplicate_real_call`): gerçek Postgres+Redis üzerinde crash senaryosu simüle edilip `TestTelephonyProvider.created` listesinin 1'de kaldığı (ikinci dial denenmediği) doğrulandı.

### #6 — Log redaksiyon bypass'ı (İKİNCİ EN KRİTİK)

`services/api/app/core/logging.py`'deki eski `_SECRET_KEY_RE` yalnız `\S+` kullandığı için `"Authorization: Bearer sk-abcd..."` biçiminde `Bearer` kelimesini yutup asıl token'ı DIŞARIDA bırakıyordu (repro: `redact("Authorization: Bearer sk-abcd1234567890ABCDEFGHIJ token=abc123")` → `sk-abcd...` sızıyordu). E-posta ve OpenAI `sk-...` anahtarları hiç yakalanmıyordu. Bu fonksiyon `JsonFormatter`'ın exception traceback'lerinde de kullanıldığı için, bir hata mesajının içine düz metin bir Authorization header veya OpenAI key sızması durumunda bu log'lara ÇIKARDI.

**Düzeltme**: `services/voice-agent/agent/redaction.py`'nin zaten test edilmiş desenleriyle (`_BEARER_RE`, `_OPENAI_KEY_RE`, `_EMAIL_RE`, düzeltilmiş `_KV_SECRET_RE`) hizalandı.

**Regresyon testi**: yeni `tests/unit/test_logging_redaction.py` (6 test) — Bearer token, OpenAI key, e-posta, telefon, plain KV secret'ın hem `redact()` fonksiyonu hem GERÇEK `configure_logging()` pipeline'ı (JSON çıktısı) üzerinden temizlendiği doğrulandı.

### Diğer düzeltmeler (özet)

- **`app/core/locks.py`**: `LockBackendUnavailable` istisnası eklendi; `redis_lock()` artık `redis.exceptions.RedisError`'ı yakalayıp bu tipe çeviriyor. `orchestrator.py` bunu `CallPolicyError("lock_backend_unavailable")`'a çeviriyor; `calls.py` route'u bunu 503'e (önceden opak 500) map ediyor.
- **`services/voice-agent/agent/job_handler.py::build_server`**: `GRACEFUL_SHUTDOWN_SECONDS` artık SDK'nın `AgentServer(shutdown_process_timeout=...)` parametresine bağlı — SIGTERM sonrası `handle()`'ın kendi `finally` temizliğine (transcript/event drain, realtime kapatma, SIP hangup) tanınan gerçek süre. SDK'nın `drain_timeout`'u (aktif çağrının bitmesini bekleme, varsayılan 1800s) BİLEREK değiştirilmedi — bu ayarın 120s'lik üst sınırını oraya bağlamak uzun bir görüşmeyi ortasında kesme riski doğururdu.
- **`compose.production.yml`**: `worker` (630s) ve `voice-agent` (360s) servislerine `stop_grace_period` eklendi — Docker'ın varsayılan 10s'lik SIGKILL süresi, hem Celery'nin `task_time_limit=600s` sonrası kendi temiz kapanışını hem SDK'nın görüşme-bitirme drain'ini önceden fiilen etkisiz bırakıyordu.
- **`services/api/app/db/session.py`**: `DB_STATEMENT_TIMEOUT_MS` (varsayılan 30000, config.py) artık `create_engine(connect_args={"options": "-c statement_timeout=..."})` ile her bağlantıya uygulanıyor — `pool_pre_ping` yalnız ölü bağlantıyı yakalar, takılı sorguyu sınırlamaz.
- **`services/voice-agent/agent/tools.py::ToolExecutor.execute`**: `TOOL_CALL_STARTED` emit'i (kuyruğu atlayıp `important=True` ile doğrudan HTTP çağrısı yapar) artık try/except İÇİNDE — kendi başarısızlığı da diğerleri gibi `ToolExecutionError`'a çevriliyor ve (best-effort) `TOOL_CALL_FAILED` emit'i deneniyor.

## 4. Yeni Test Dosyaları / Testler

| Dosya | Yeni test sayısı | Kapsam |
|---|---|---|
| `services/api/tests/integration/test_call_tasks.py` | 7 (yeni dosya) | place_call happy-path, skip-if-not-queued, **mükerrer dial önleme**, watchdog force-close + hangup, watchdog no-op (terminal), operatör hangup, process_terminal_call |
| `services/api/tests/unit/test_locks.py` | 1 | Redis ConnectionError → `LockBackendUnavailable` |
| `services/api/tests/integration/test_orchestrator.py` | 1 | Route seviyesinde `lock_backend_unavailable` → `CallPolicyError` |
| `services/api/tests/unit/test_logging_redaction.py` | 6 (yeni dosya) | Bearer/OpenAI-key/e-posta/telefon redaksiyonu, gerçek JSON pipeline |
| `services/api/tests/unit/test_db_session.py` | 1 (yeni dosya) | `statement_timeout` GUC'unun gerçek bağlantıya uygulandığı |
| `services/voice-agent/tests/test_runtime_adapters.py` | 3 | `LiveKitRealtimeSessionAdapter.start()` bağlantı hatası + timeout sarmalama, `build_server`'ın `shutdown_process_timeout`'u doğru geçirdiği |
| `services/voice-agent/tests/test_errors.py` | 3 (yeni dosya, 17 parametrized durum) | `classify_sip_status` RFC 3261 eşlemesinin TÜM dalları |
| `services/voice-agent/tests/test_tools.py` | 2 | STARTED/FAILED emit hatalarının sınıflandırılması |

**Toplam**: backend 160 → **176** test (+16), voice-agent 117 → **140** test (+23).

## 5. Doğrulama

| Kontrol | Sonuç |
|---|---|
| `services/api` — `ruff check app tests` | Temiz |
| `services/api` — `mypy app` | Temiz (81 dosya) |
| `services/api` — `pytest -q` | **176 passed** |
| `services/voice-agent` — `ruff check agent tests` | Temiz |
| `services/voice-agent` — `mypy agent` | Temiz (16 dosya) |
| `services/voice-agent` — `mypy agent tests` (geniş) | Temiz (30 dosya) |
| `services/voice-agent` — `pytest -q` | **140 passed** |
| `docker compose --env-file .env.production -f compose.production.yml config -q` | Geçti (yeni `stop_grace_period` + `DB_STATEMENT_TIMEOUT_MS` sonrası) |

Frontend bu turda değiştirilmedi; Aşama 7'deki durumu (tsc/eslint/vitest temiz) geçerliliğini koruyor.

## 6. Bilinçli Olarak Ertelenen Maddeler

1. **`watchdog_sweep`'in kendi toplu-sorgu yoluna özel bir test yazılmadı** — `_force_close` (asıl temizlik mantığı) `test_watchdog_check_force_closes_active_call_and_hangs_up` ile zaten dolaylı olarak tam kapsanıyor; `watchdog_sweep` yalnız bunu "stale_before" filtresiyle toplu çağıran ince bir sarmalayıcı.
2. **SDK'nın tool-call-through-model garantisi için repo içi entegrasyon testi yazılmadı** — `livekit/agents/voice/generation.py`'deki geniş `except BaseException` + her zaman `_tool_completed` çağrısı kaynak okumayla doğrulandı; bu SDK'nın kendi sözleşmesi, bizim kodumuzun test etmesi gereken bir davranış değil.
3. **Backend API/frontend servislerine `stop_grace_period` eklenmedi** — bunlar durumsuz (stateless) HTTP servisleri; SIGTERM sonrası yarım kalan bir HTTP isteği zaten istemci tarafından yeniden denenebilir, worker/voice-agent'taki "aktif görüşme/görev" riskiyle aynı kategoride değil.

## 7. Sonuç

Kritik/yüksek veya commit-engelleyici orta seviye açık bulgu **yok** — ikisi vardı (#2 mükerrer arama, #6 log sızıntısı), ikisi de düzeltildi ve regresyon testiyle kilitlendi. Aşama 9'a (güvenlik son taraması) geçiş için engel yok.
