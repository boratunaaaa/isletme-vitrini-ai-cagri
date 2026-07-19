# Aşama 9 — Güvenlik Son Taraması

Tarih: 2026-07-19
Kapsam: Aşama 8 commit (`4974455`) sonrası; authn/authz, CSRF/CORS, injection sınıfları, IDOR, redaksiyon, cookie/session, dış yüzey (docs/debug) denetimi.

## 1. Yöntem

15 alan (parola/oturum, RBAC kapsaması, CSRF, CORS/TrustedHost, rate limiting, injection sınıfları [SQL/shell/SSRF/redirect/XSS], dosya yükleme, log injection, docs/debug uç nokta erişimi, admin/backup işlemleri, frontend env sızıntısı, IDOR/kaynak sahipliği, CSV formül injection, cookie bayrakları, secret loglama) read-only bir ajanla dosya+satır bazında değerlendirildi; bulunan her GAP bizzat okunup doğrulandı ve düzeltildi.

## 2. Sonuç: Kritik/Yüksek Açık Bulgu Yok

Tarama başlangıçta **2 gerçek yüksek-orta seviye bulgu** ve **3 orta/düşük seviye sertleştirme fırsatı** buldu. Hepsi bu turda kapatıldı; kritik/yüksek veya commit-engelleyici orta seviye **açık bulgu kalmadı**.

| # | Bulgu | Ciddiyet | Durum |
|---|---|---|---|
| 1 | `demo_wa_link` endpoint'i `PHONE_REVEAL` yerine `CALL_INITIATE` istiyordu — `sales_agent` rolü (PHONE_REVEAL'ı YOK) tam açık telefon numarasını farklı bir yetkili endpoint üzerinden alabiliyordu | **Yüksek** (RBAC sınır ihlali, PII sızıntısı) | **Kapatıldı** |
| 2 | CSV export (`/leads/export`) Excel/Sheets formül enjeksiyonuna (CWE-1236) karşı sanitize edilmiyordu | Orta-Yüksek | **Kapatıldı** |
| 3 | Login brute-force koruması yalnız `{ip}:{email}` anahtarıyla çalışıyordu — IP döndüren bir saldırgan tek bir hesabı dağıtık şekilde sınırsız deneyebilirdi | Orta | **Kapatıldı** |
| 4 | `reveal-phone` ve `/leads/export` uç noktalarında (login dışında) hiçbir rate limit yoktu — yetkili ama ele geçirilmiş bir hesap script ile toplu PII sızdırabilirdi | Orta | **Kapatıldı** |
| 5 | `/docs`, `/redoc`, `/openapi.json` uygulama kodunda hiç kapatılmıyordu — yalnız Caddy proxy kurallarıyla (TEK katman) dışarıya kapalıydı | Orta-Düşük (derinlemesine savunma) | **Kapatıldı** |

## 3. Bulgu Detayları ve Düzeltmeler

### #1 — RBAC sınır ihlali (EN CİDDİ)

`services/api/app/api/routes/ops.py::demo_wa_link` (GET `/demo-requests/{id}/wa-link`) `decrypt_pii(lead.phone_ciphertext)` çağırıp tam E.164 numarayı bir `wa.me/<numara>?text=...` linkine gömüp JSON'da döndürüyordu — ama yetki kontrolü `Permission.CALL_INITIATE` idi. RBAC matrisinde (`app/core/rbac.py`) `sales_agent` rolü `CALL_INITIATE`'a SAHİP ama `PHONE_REVEAL`'a SAHİP DEĞİL — yani bu rol, dedicated `reveal-phone` endpoint'inde (doğru şekilde 403 alırken) bu endpoint'ten aynı PII'ye erişebiliyordu.

**Düzeltme**: `demo_wa_link`'in yetki bağımlılığı `Permission.PHONE_REVEAL`'e çevrildi (`services/api/app/api/routes/ops.py`).
**Regresyon testi**: `tests/integration/test_authorization.py::test_sales_agent_cannot_reveal_phone_via_demo_wa_link` — `sales_agent` → 403, `owner` → 200 + numara doğrulaması.

### #2 — CSV formül enjeksiyonu

`services/api/app/api/routes/leads.py::export_leads`, kullanıcı/import kontrollü alanları (`business_name`, `sector`, `city`, `district`, `website`, `demo_link`) hiçbir sanitizasyon olmadan CSV hücresine yazıyordu. `=HYPERLINK(...)` gibi bir `business_name`, dosyayı Excel/Sheets'te açan kişi için formül olarak çalışabilirdi.

**Düzeltme**: standart OWASP mitigasyonu — `=`/`+`/`-`/`@`/tab/CR ile başlayan hücre değerleri önüne görünürlüğü bozmayan bir tek tırnak (`'`) eklenerek düz metne zorlanıyor (`_csv_safe()` yardımcı fonksiyonu).
**Regresyon testleri**: `tests/unit/test_csv_export_safety.py` (7 test, birim seviyesi), `tests/integration/test_leads_export.py::test_export_neutralizes_formula_injection_in_business_name` (gerçek HTTP endpoint üzerinden uçtan uca).

### #3 — Dağıtık brute-force

`services/api/app/api/routes/auth.py::login`, yalnız `{ip}:{email}` anahtarıyla hem 5/60s throttle hem 10-başarısızlık/15dk kilit uyguluyordu. Kaynak IP'sini döndüren bir saldırgan her IP için TAZE bir sayaç alır — tek bir bilinen hesabı dağıtık şekilde brute-force etmek fiilen sınırsız kalırdı.

**Düzeltme**: ikinci, hesap-seviyeli (yalnız e-posta) bir kilit sayacı eklendi (`account:{email}`, eşik 20 — IP-seviyeli eşikten (10) yüksek tutuldu ki gerçek kullanıcıyı yanlışlıkla kilitleme riski düşük kalsın, bu SAVUNMA DERİNLİĞİ katmanı, ana mekanizma IP-seviyeli kalmaya devam ediyor).
**Regresyon testi**: `tests/integration/test_auth.py::test_distributed_brute_force_triggers_account_level_lockout` — 20 farklı IP'den başarısız deneme, 21. deneme (hiç kullanılmamış YENİ bir IP'den) 429 dönüyor.

### #4 — PII-scraping uç noktalarında rate limit yokluğu

`reveal-phone` (permission-gated ama throttle'sız — yetkili-ama-ele-geçirilmiş bir hesap script ile TÜM veritabanını tek tek numara açığa çıkararak sızdırabilirdi) ve `/leads/export` (tekrarlanan tam-veritabanı export'ları) kullanıcı-başına rate limit'e kavuşturuldu (sırasıyla 60/60s, 5/60s — mevcut `check_rate_limit()` yardımcı fonksiyonu yeniden kullanıldı, yeni bir soyutlama eklenmedi).
**Regresyon testleri**: `test_authorization.py::test_reveal_phone_is_rate_limited_per_user`, `test_leads_export.py::test_export_is_rate_limited_per_user`.

*(Not: call-initiate zaten `MAX_DAILY_CALLS`/`MAX_CONCURRENT_CALLS` global politika kapılarıyla makul ölçüde sınırlı olduğu için ayrıca dokunulmadı.)*

### #5 — Docs/redoc/openapi derinlemesine savunma

`services/api/app/main.py::create_app`, production'da `docs_url`/`redoc_url`/`openapi_url`'i `None`'a çeviriyor artık — önceden bunlar yalnız Caddy'nin proxy kurallarıyla (yalnız `/api/*` ve `/health`,`/ready` backend'e yönlendirilir) dışarıya kapalıydı; backend container'ı herhangi bir nedenle doğrudan erişilebilir hale gelirse (debug, port-forward, altyapı değişikliği) interaktif API dokümantasyonu kimlik doğrulamasız açığa çıkardı.
**Regresyon testleri**: `tests/test_app_smoke.py::test_docs_disabled_in_production`, `test_docs_enabled_outside_production`.

## 4. Doğrulanan SOLID Alanlar (değişiklik gerekmedi)

- Parola hashleme: Argon2id, OWASP üzeri parametreler.
- Oturum token entropisi: 256-bit CSPRNG, sunucu tarafında Redis'te SHA-256 digest ile saklanıyor.
- Oturum süresi/idle-timeout: hem mutlak hem kayan pencere sunucu tarafında (Redis) uygulanıyor.
- Logout/rol değişikliği/parola sıfırlama: gerçek sunucu-taraflı oturum iptali (`destroy_session`/`destroy_all_sessions_for_user`).
- RBAC kapsaması: tüm mutasyon/hassas-okuma route'ları `require_permission` bağımlılığı taşıyor (yalnız #1 istisnaydı, düzeltildi).
- CSRF: `get_current_user` içinde merkezi double-submit + HMAC doğrulaması, tüm mutasyon route'larında tekdüze.
- CORS/TrustedHost: `.env`'den geliyor, wildcard yok, production'da zorunlu.
- SQL injection: kullanıcı girdisiyle inşa edilen raw SQL/f-string yok; tüm `order_by` alanları statik sütun referansı.
- Shell injection: backup script'leri secret'ları argv'ye koymuyor, `--target-db` allowlist regex ile doğrulanıyor.
- SSRF: tek değişken hedefli HTTP çağrısı (Google Places) sabit host'a, yalnız path segmentine kullanıcı girdisi giriyor.
- Open redirect: `safe-redirect.ts` sağlam (backslash/control-char/`//` reddi, same-origin zorunluluğu).
- XSS: `dangerouslySetInnerHTML` hiçbir yerde kullanılmıyor.
- Dosya yükleme: 30MB sınır, bellek-içi parse, path traversal/exec riski yok.
- Log injection: JSON formatlı loglar, gömülü newline'lar JSON-escape edilir.
- Backup/restore: yalnız operatör/CLI erişimli (`profiles: ["tools"]`), hiçbir API route'undan tetiklenemiyor.
- Frontend secret sızıntısı: yalnız non-secret `NEXT_PUBLIC_API_URL` bulundu.
- Cookie bayrakları: session cookie `httponly+secure(prod)+samesite=lax`; her login'de yeni rastgele token (session fixation riski yok).
- Secret/token loglama: request-logging middleware yalnız method/path/süre loglar, header/body loglamaz.

## 5. Doğrulama

| Kontrol | Sonuç |
|---|---|
| `services/api` — `ruff check app tests` | Temiz |
| `services/api` — `mypy app` | Temiz (81 dosya) |
| `services/api` — `pytest -q` | **192 passed** (Aşama 8 sonrası 176 → +16) |

Frontend ve voice-agent bu turda değiştirilmedi; önceki aşamalardaki temiz durumları geçerliliğini koruyor.

## 6. Bilinçli Olarak Ertelenen Maddeler

1. **XLSX/zip-bomb/XXE parsing kütüphanesi iç güvenliği** (`services/importer.py`'nin kullandığı openpyxl/pandas) — dedicated bir pass gerektirir, bu turun kapsamı dışında bırakıldı; mevcut 30MB boyut sınırı pratik riski azaltıyor.
2. **`CORS_ORIGINS=*` için açık startup-time reddi eklenmedi** — mevcut `.env.production.example` zaten somut bir origin veriyor ve hiçbir kod yolu wildcard'ı kabul etmiyor; yalnızca yazılı bir "asla `*` yapma" uyarısı `docs/production/SECURITY_CHECKLIST.md`'de zaten var (Aşama 6). Yeni bir validasyon kuralı eklemek bu turun kapsamını aştı.

## 7. Sonuç

Kritik/yüksek seviyede açık bulgu **yok**. Bulunan 2 ciddi bulgu (RBAC sınır ihlali, CSV formül enjeksiyonu) ve 3 sertleştirme fırsatı (dağıtık brute-force, PII-scraping rate limit, docs derinlemesine savunma) tamamı düzeltildi ve regresyon testiyle kilitlendi. Aşama 10'a (observability/operasyon) geçiş için engel yok.
