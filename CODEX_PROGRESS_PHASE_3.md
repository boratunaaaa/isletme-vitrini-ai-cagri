# CODEX Progress Phase 3

## 1. Amaç

Internal Voice-Agent API sözleşmesi eklendi. Bu aşamada voice-agent runtime, OpenAI Realtime, LiveKit SIP, Netgsm, gerçek telefon araması, frontend, deployment, commit veya push yapılmadı.

## 2. Başlangıç durumu

Aşama 1 ve Aşama 2 sonrası FastAPI uygulaması, Alembic, bootstrap/seed, kritik domain testleri ve 96 testlik backend seti çalışır durumdaydı. Aşama 3 başlangıç kabulü: `pytest` önceki durumda 96 passed, 1 warning.

## 3. Oluşturulan endpointler

Prefix: `/api/internal/v1`

- `GET /health`
- `GET /calls/{call_id}/bootstrap`
- `GET /calls/{call_id}/dial-plan`
- `POST /calls/{call_id}/events`
- `POST /calls/{call_id}/transcript-turns`
- `POST /calls/{call_id}/usage`
- `POST /calls/{call_id}/complete`
- 12 adet kontrollü tool endpointi

## 4. Internal authentication

`require_internal_service` dependency’si Bearer token doğrulaması yapar. Current ve previous token desteklenir. Boş token reddedilir. Constant-time comparison `verify_internal_token_with_rotation` ile yapılır. Normal kullanıcı session cookie’si internal endpointlere erişim sağlamaz.

## 5. Bootstrap contract

Bootstrap endpointi call, lead, campaign, aktif prompt, knowledge base, telephony tanımlayıcıları ve policy bilgisini döndürür. Tam telefon yalnız internal auth sonrası decrypt edilir. Suppressed veya terminal call reddedilir. Response secret içermez.

## 6. Dial plan contract

Dial plan endpointi call policy ve suppression kontrolü sonrası telefon, trunk id, caller id, room name ve participant identity döndürür. SIP username/password, Netgsm credential ve LiveKit secret response’a eklenmez.

## 7. Event ingestion

Lifecycle event endpointi tanımlı event tiplerini kabul eder, payload sanitize eder, state machine geçişlerini güvenli uygular ve duplicate eventleri idempotent işler. Aynı ID farklı payload için `409` döner.

## 8. Transcript ingestion

Final transcript turn’leri `call_transcript_turns` tablosuna redacted metinle kaydedilir. Storage kapalıysa içerik saklanmaz. Partial turn sınırsız biriktirilmez. Naive datetime, geçersiz zaman aralığı ve uzun metin reddedilir.

## 9. Usage ingestion

Usage endpointi incremental/final usage eventlerini işler. Negatif veya aşırı büyük tokenlar reddedilir. Provider/model call metadata ile uyumluluk doğrulanır. Maliyet `cost_service.py` üzerinden Decimal ile hesaplanır. Pricing yoksa `PRICING_NOT_CONFIGURED` döner.

## 10. Agent tool endpointleri

Eklenen tool’lar:

- `get-service-information`
- `get-package-information`
- `request-demo-link`
- `schedule-callback`
- `mark-interested`
- `mark-not-interested`
- `mark-wrong-number`
- `mark-decision-maker-unavailable`
- `add-to-suppression-list`
- `request-human-transfer`
- `finalize-call-outcome`
- `end-call-safely`

Her tool strict schema, internal auth, idempotency ve terminal call kontrolü uygular.

## 11. Completion contract

Completion endpointi idempotent şekilde terminal state uygular. Finalize yapılmamışsa deterministic fallback outcome kullanır, campaign lead sonucunu günceller ve duplicate completion’da ikinci yan etki üretmez.

## 12. İdempotency yapısı

`internal_invocations` tablosu eklendi. Aynı external ID ve aynı sanitize edilmiş canonical payload önceki sonucu döndürür. Aynı ID farklı payload `DUPLICATE_EVENT_CONFLICT` üretir. Result snapshot güvenli JSON olarak saklanır.

## 13. Error modeli

Internal API hata formatı:

```json
{"error":{"code":"VALIDATION_ERROR","message":"Request validation failed.","request_id":"..."}}
```

Auth, validation ve domain hatalarında telefon, transcript, token, secret, connection string veya stack trace dönmez.

## 14. Pydantic şemaları

Internal request/response şemaları `services/api/app/schemas/internal/voice_agent.py` altında toplandı. Extra alanlar reddedilir; timezone-aware timestamp, event/tool ID formatı, string limitleri ve token üst sınırları doğrulanır.

## 15. Yeni veritabanı modelleri

- `InternalInvocation`
- `CallTranscriptTurn`

Modeller `services/api/app/models/internal.py` içinde tanımlandı ve `app.models` export listesine eklendi.

## 16. Yeni migrationlar

Yeni revision: `20260718_0003_internal_voice_agent_contract.py`.

Zorunlu migration düzeltmesi: `20260717_0001_initial_schema.py` dinamik `Base.metadata.create_all()` kullandığı için yeni Phase 3 modellerini de ilk migration içinde yaratıyordu. Bu, `0003` ile duplicate table hatası üretiyordu. İlk migration legacy tablo setiyle sınırlandırıldı; internal tablolar yalnız `0003` revision’ında oluşturuluyor.

## 17. Security kontrolleri

Testlenen kontroller:

- Token yok/yanlış token `401`.
- Previous token rotasyonu çalışıyor.
- Normal user session internal endpointte yetki sağlamıyor.
- Internal validation raw input döndürmüyor.
- Bootstrap/dial-plan dışında full phone dönmüyor.
- Secret, SIP password, API key ve internal token response’larda yok.
- Transcript ve event payload redaction uygulanıyor.

## 18. Eklenen testler

Yeni test dosyası: `services/api/tests/integration/test_internal_voice_agent_api.py`.

15 test eklendi. Kapsam: auth, bootstrap, dial-plan, events, transcript, usage, tools, completion ve security no-leak kontrolleri.

## 19. Pytest sonucu

`uv run pytest -q`

Sonuç: `111 passed, 1 warning in 11.45s`.

Warning: üçüncü taraf `fastapi.testclient` / Starlette `httpx` deprecation warning. Filtrelenmedi.

## 20. Coverage sonucu

`uv run pytest --cov=app --cov-report=term-missing`

Sonuç: `111 passed, 1 warning`, toplam coverage `%72`.

Seçilmiş ilgili modüller:

- `app/api/routes/internal/calls.py`: `%82`
- `app/api/routes/internal/common.py`: `%88`
- `app/api/routes/internal/health.py`: `%81`
- `app/api/routes/internal/tools.py`: `%92`
- `app/schemas/internal/voice_agent.py`: `%99`
- `app/models/internal.py`: `%100`
- `app/services/internal_contract.py`: `%96`

Düşük kalan genel coverage alanları bu aşama dışındaki provider/task modülleridir.

## 21. Ruff sonucu

`uv run ruff check app tests`

Sonuç: `All checks passed!`

## 22. MyPy sonucu

`uv run mypy app`

Sonuç: `Success: no issues found in 80 source files`.

## 23. Migration doğrulaması

Çalıştırılan komutlar:

- `uv run alembic upgrade head`
- `uv run alembic downgrade -1`
- `uv run alembic upgrade head`
- `uv run alembic downgrade base`
- `uv run alembic upgrade head`

Sonuç: tüm migration döngüleri geçti.

Not: Test sırasında `ivac_test` DB’de önceki yarım migration denemesinden kalan internal tablolar temizlendi ve test şeması migration doğrulaması için sıfırlandı. Volume silinmedi.

## 24. Docker config sonucu

`docker compose -f docker-compose.dev.yml config`

Sonuç: config başarıyla üretildi.

## 25. Değiştirilen production dosyaları

- `.env.example`
- `services/api/app/config.py`
- `services/api/app/core/security.py`
- `services/api/app/deps.py`
- `services/api/app/main.py`
- `services/api/app/models/__init__.py`
- `services/api/app/models/internal.py`
- `services/api/app/services/internal_contract.py`
- `services/api/app/api/routes/internal/__init__.py`
- `services/api/app/api/routes/internal/common.py`
- `services/api/app/api/routes/internal/health.py`
- `services/api/app/api/routes/internal/calls.py`
- `services/api/app/api/routes/internal/tools.py`
- `services/api/app/schemas/internal/__init__.py`
- `services/api/app/schemas/internal/voice_agent.py`
- `services/api/alembic/versions/20260717_0001_initial_schema.py`
- `services/api/alembic/versions/20260718_0003_internal_voice_agent_contract.py`

## 26. Bilinen eksikler

- Voice-agent runtime henüz yok.
- OpenAI Realtime session oluşturma yok.
- LiveKit/SIP participant oluşturma yok.
- Netgsm bağlantısı yok.
- Completion sonrası gerçek queue retry enqueue entegrasyonu sınırlı domain update seviyesinde kaldı.
- SSE publish güvenli event çağrıları mevcut event bus üzerinden yapılıyor; gerçek frontend tüketimi bu aşama dışında.

## 27. Voice-agent aşaması için hazır contract

Voice-agent artık bootstrap, dial-plan, event ingestion, transcript ingestion, usage ingestion, tool calls ve completion için backend contract’a sahip. Contract dokümanı: `docs/internal-voice-agent-api.md`.

## 28. Sonraki önerilen aşama

Aşama 4 için öneri: fake provider ile worker/orchestrator ve internal API lifecycle uçtan uca testini genişletmek, ardından voice-agent runtime implementasyonuna geçmeden önce LiveKit/OpenAI adaptörlerinin mock contract testlerini yazmak.

## 29. Git durumu

`git status --short` çıktısı tüm proje dosyalarını untracked gösteriyor; repo henüz commitlenmiş bir baseline’a sahip görünmüyor. Commit, push, reset, checkout, clean veya stash yapılmadı.
