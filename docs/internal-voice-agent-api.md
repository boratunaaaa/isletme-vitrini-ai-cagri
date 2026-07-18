# Internal Voice-Agent API

Bu sözleşme ileride geliştirilecek voice-agent servisinin backend ile konuşacağı dahili API yüzeyidir. Bu aşama OpenAI Realtime, LiveKit, SIP veya Netgsm runtime çağrısı içermez.

## Authentication

Tüm internal endpointler `Authorization: Bearer <INTERNAL_SERVICE_TOKEN>` başlığı ister.

Desteklenen environment değişkenleri:

- `INTERNAL_SERVICE_TOKEN`
- `INTERNAL_SERVICE_TOKEN_PREVIOUS`
- `INTERNAL_SERVICE_NAME`

Token karşılaştırması constant-time yapılır. Previous token yalnız rotasyon penceresi için kabul edilir. Token DB’ye yazılmaz, response veya loglarda gösterilmez. Normal kullanıcı session cookie’si internal endpointlere erişim sağlamaz.

## Endpoint Listesi

Prefix: `/api/internal/v1`

- `GET /health`
- `GET /calls/{call_id}/bootstrap`
- `GET /calls/{call_id}/dial-plan`
- `POST /calls/{call_id}/events`
- `POST /calls/{call_id}/transcript-turns`
- `POST /calls/{call_id}/usage`
- `POST /calls/{call_id}/complete`
- `POST /calls/{call_id}/tools/get-service-information`
- `POST /calls/{call_id}/tools/get-package-information`
- `POST /calls/{call_id}/tools/request-demo-link`
- `POST /calls/{call_id}/tools/schedule-callback`
- `POST /calls/{call_id}/tools/mark-interested`
- `POST /calls/{call_id}/tools/mark-not-interested`
- `POST /calls/{call_id}/tools/mark-wrong-number`
- `POST /calls/{call_id}/tools/mark-decision-maker-unavailable`
- `POST /calls/{call_id}/tools/add-to-suppression-list`
- `POST /calls/{call_id}/tools/request-human-transfer`
- `POST /calls/{call_id}/tools/finalize-call-outcome`
- `POST /calls/{call_id}/tools/end-call-safely`

Internal routerlar public OpenAPI şemasından gizlenir.

## Bootstrap

`GET /calls/{call_id}/bootstrap` voice-agent için güvenli çağrı bağlamını döndürür.

Örnek response:

```json
{
  "call_id": "00000000-0000-0000-0000-000000000001",
  "lead": {
    "business_name": "Örnek İşletme",
    "sector": "Hizmet",
    "city": "İstanbul",
    "district": "Üsküdar",
    "website": "https://example.invalid",
    "phone_e164": "+90555***2233",
    "phone_last_four": "2233"
  },
  "campaign": {
    "campaign_id": "00000000-0000-0000-0000-000000000002",
    "name": "Demo Kampanya",
    "conversation_engine": "openai_realtime",
    "model": "gpt-realtime-2.1-mini",
    "voice": "marin",
    "max_call_duration_seconds": 300
  },
  "agent_configuration": {
    "prompt_version_id": "00000000-0000-0000-0000-000000000003",
    "system_prompt": "PII-safe prompt",
    "opening_script": "Merhaba...",
    "objective": "Demo ilgisini ölç",
    "tool_policy": {}
  },
  "knowledge_base": [],
  "telephony": {
    "outbound_trunk_id": "trunk-id",
    "caller_id": "+90216***0000",
    "sip_transport": "udp",
    "codec_preferences": []
  },
  "policy": {
    "recording_enabled": false,
    "transcript_storage_enabled": true,
    "human_transfer_enabled": false
  }
}
```

Tam telefon yalnız internal auth sonrası decrypt edilir. Suppression listesindeki veya terminal durumdaki çağrılar bootstrap edilemez. Response API key, SIP password, LiveKit secret, Netgsm credential veya internal token içermez.

## Dial Plan

`GET /calls/{call_id}/dial-plan` SIP participant oluşturmak için secret olmayan operasyonel bilgileri döndürür.

```json
{
  "call_id": "00000000-0000-0000-0000-000000000001",
  "phone_e164": "+90555***2233",
  "sip_trunk_id": "trunk-id",
  "caller_id": "+90216***0000",
  "room_name": "call-00000000-0000-0000-0000-000000000001",
  "participant_identity": "phone-00000000-0000-0000-0000-000000000001",
  "participant_name": "Örnek İşletme",
  "max_call_duration_seconds": 300
}
```

Dial plan call policy ve suppression kontrolünü tekrar yapar. SIP username/password ve provider secretları response’a eklenmez.

## Event Türleri

`POST /calls/{call_id}/events` şu tipleri kabul eder:

- `agent_job_started`
- `agent_job_failed`
- `sip_participant_creating`
- `dialing`
- `ringing`
- `answered`
- `agent_session_started`
- `user_speech_started`
- `user_speech_stopped`
- `agent_speech_started`
- `agent_speech_stopped`
- `tool_call_started`
- `tool_call_completed`
- `tool_call_failed`
- `transfer_started`
- `transfer_completed`
- `transfer_failed`
- `usage_updated`
- `call_disconnected`
- `agent_session_ended`

`dialing`, `ringing`, `answered` ve `agent_session_started` state machine üzerinden durum geçişi yapabilir. Geçersiz geçişler güvenli hata döndürür. Payload sanitize edilir ve boyut sınırlıdır.

## Tool Şemaları

Her tool request `tool_call_id` ve `occurred_at` içerir. Extra alanlar reddedilir. Aynı `tool_call_id` ve aynı payload önceki sonucu döndürür; aynı ID farklı payload `409` üretir.

Mutating tool’lar terminal call durumunda reddedilir. Agent serbest DB güncellemesi yapamaz.

Örnek finalize request:

```json
{
  "tool_call_id": "tool-001",
  "occurred_at": "2026-07-18T12:00:00Z",
  "outcome": "demo_requested",
  "safe_summary": "Demo bağlantısı istendi.",
  "interest_level": "high",
  "callback_at": null,
  "demo_requested": true,
  "transfer_requested": false,
  "notes": []
}
```

## Error Kodları

Internal API hata formatı:

```json
{
  "error": {
    "code": "CALL_NOT_DIALABLE",
    "message": "Call cannot be dialed in its current state.",
    "request_id": "request-id"
  }
}
```

Desteklenen kodlar:

- `INTERNAL_AUTH_REQUIRED`
- `INTERNAL_AUTH_INVALID`
- `CALL_NOT_FOUND`
- `CALL_NOT_DIALABLE`
- `CALL_ALREADY_TERMINAL`
- `LEAD_NOT_FOUND`
- `CAMPAIGN_NOT_FOUND`
- `PROMPT_NOT_CONFIGURED`
- `PRICING_NOT_CONFIGURED`
- `SUPPRESSED_PHONE`
- `INVALID_STATE_TRANSITION`
- `DUPLICATE_EVENT_CONFLICT`
- `TRANSCRIPT_STORAGE_DISABLED`
- `TOOL_CALL_INVALID`
- `HUMAN_TRANSFER_DISABLED`
- `VALIDATION_ERROR`

Hatalar telefon, transcript, token, credential, connection string veya stack trace içermez.

## Idempotency

Internal idempotency `internal_invocations` tablosuyla tutulur:

- `call_id`
- `external_id`
- `event_type`
- `payload_hash`
- `processing_status`
- `result_snapshot`
- `created_at`
- `processed_at`

Hash sanitize edilmiş canonical payload üzerinden hesaplanır. Aynı ID ve aynı payload önceki sonucu döndürür. Aynı ID ve farklı payload `409 DUPLICATE_EVENT_CONFLICT` üretir.

## Completion

`POST /calls/{call_id}/complete` görüşmenin GERÇEKTEN sona erdiğini bildirir (2026-07-18 düzeltmesi — bkz. `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`).

```json
{
  "completion_event_id": "completion-<call_id>",
  "disconnect_reason": "sip_failure",
  "ended_at": "2026-07-18T12:00:05Z",
  "duration_seconds": 0,
  "final_usage_event_id": null,
  "sip_reason": "busy"
}
```

- `disconnect_reason`: serbest metin (`remote_hangup`, `agent_hangup`, `timeout`, `sip_failure`, `openai_failure`, `agent_error`, `completed`).
- `sip_reason` (opsiyonel, yalnız `disconnect_reason == "sip_failure"` iken anlamlı): RFC 3261 SIP durum koduna göre sınıflandırılmış neden — `busy`, `no_answer`, `rejected`, `cancelled`, `timeout`, `authentication_error`, `trunk_error`, `redirect_unsupported`, `unknown_sip_failure`. Backend bunu call status'una (`busy`/`no_answer`/`rejected`/`cancelled`, aksi halde `failed`) ve dolayısıyla kampanya retry zamanlamasına (`compute_next_retry`, durum bazlı çarpan) taşır. Alan opsiyoneldir — eski voice-agent sürümleri göndermese de `/complete` eskisi gibi `completed`/`failed`'a düşer (geriye dönük uyumlu).

Backend, terminal durum uygulandıktan sonra lead/campaign_lead etkilerini **tek doğru kaynaktan** (`campaign_service.handle_call_terminal` + `maybe_complete_campaign`) uygular — retry zamanlaması call status'a göre otomatik hesaplanır.

## Transcript Retention

`POST /calls/{call_id}/transcript-turns` yalnız final turn’leri kalıcı saklar. `TRANSCRIPT_STORAGE_ENABLED=false` ise içerik saklanmaz, deterministic ignored response döner. Transcript metni redaction pipeline’dan geçer; telefon ve email gibi hassas değerler maskelenir. Partial transcriptler sınırsız biriktirilmez.

## Usage ve Maliyet

`POST /calls/{call_id}/usage` incremental ve final usage eventlerini kabul eder. Token değerleri negatif veya aşırı büyük olamaz. Model/provider call metadata ile uyumlu olmalıdır. Maliyet mevcut `cost_service.py` ile Decimal olarak hesaplanır. Pricing kaydı yoksa sessiz `0` yazılmaz; `PRICING_NOT_CONFIGURED` döner.

`usage_source` değerleri:

- `provider_reported`
- `estimated`
- `unavailable`

## Secret ve PII Kuralları

- Full phone yalnız yetkili bootstrap ve dial-plan response’unda döner.
- Token, API key, SIP password, LiveKit secret ve Netgsm credential hiçbir response’a eklenmez.
- Payload, transcript ve tool notları sanitize edilir.
- Internal validation hataları raw request input döndürmez.
- Response ve loglarda transcript veya full phone bulunmaması testlenmiştir.

## Voice-Agent Entegrasyon Sırası

1. Worker call job üretir.
2. Voice-agent job aldığında `/bootstrap` ile context alır.
3. Dial başlamadan `/dial-plan` çağrılır.
4. Runtime olayları `/events` ile gönderilir.
5. Final transcript turn’leri `/transcript-turns` ile gönderilir.
6. Provider usage `/usage` ile gönderilir.
7. Agent kontrollü aksiyonları tool endpointleriyle bildirir.
8. Bağlantı bittiğinde `/complete` çağrılır.

## Örnek Agent Lifecycle

1. `GET /calls/{call_id}/bootstrap`
2. `POST /calls/{call_id}/events` with `agent_job_started`
3. `GET /calls/{call_id}/dial-plan`
4. `POST /calls/{call_id}/events` with `dialing`, `ringing`, `answered`
5. `POST /calls/{call_id}/transcript-turns`
6. `POST /calls/{call_id}/tools/request-demo-link`
7. `POST /calls/{call_id}/usage`
8. `POST /calls/{call_id}/tools/finalize-call-outcome`
9. `POST /calls/{call_id}/complete`
