# 1. Amaç

Aşama 2 kapsamında backend domain kurallarını testlerle doğrulamak, testlerin ortaya çıkardığı gerçek güvenlik/policy eksiklerini minimum production değişikliğiyle düzeltmek ve migration tabanının hâlâ çalıştığını kanıtlamak hedeflendi.

# 2. Başlangıç durumu

Aşama 1 sonunda FastAPI app, router wiring, Alembic altyapısı, ilk migration, bootstrap/seed komutları ve temel smoke testleri çalışır durumdaydı. Başlangıçta kritik domain davranışları için kapsamlı test yoktu. Aşama 1 uyarısı FastAPI TestClient kaynaklı üçüncü taraf deprecation uyarısıydı.

# 3. Eklenen test dosyaları

- `services/api/tests/unit/test_phone_normalization.py`
- `services/api/tests/unit/test_crypto.py`
- `services/api/tests/unit/test_rbac.py`
- `services/api/tests/unit/test_call_state_machine.py`
- `services/api/tests/unit/test_call_service.py`
- `services/api/tests/unit/test_call_policy.py`
- `services/api/tests/unit/test_retry.py`
- `services/api/tests/unit/test_locks.py`
- `services/api/tests/unit/test_cost_service.py`
- `services/api/tests/integration/test_auth.py`
- `services/api/tests/integration/test_authorization.py`
- `services/api/tests/integration/test_lead_import.py`
- `services/api/tests/integration/test_duplicate_leads.py`
- `services/api/tests/integration/test_orchestrator.py`
- `services/api/tests/fixtures/leads_tr.csv`
- `services/api/tests/fixtures/leads_en.json`

# 4. Değiştirilen production dosyaları

- `services/api/app/core/crypto.py`
- `services/api/app/core/phone.py`
- `services/api/app/core/locks.py`
- `services/api/app/api/routes/auth.py`
- `services/api/app/models/lead.py`
- `services/api/alembic.ini`
- `services/api/alembic/versions/20260717_0002_unique_lead_phone_hash.py`
- `services/api/pyproject.toml`

# 5. Telefon normalizasyon testleri

TR formatları E.164 `+905321234567` olarak doğrulandı. Boş, kısa, uzun ve harf içeren girişler kontrollü `PhoneValidationError` üretiyor. Mevcut politika geçerli yabancı numaraları kabul ediyor fakat `is_tr_mobile=False` işaretliyor.

# 6. Crypto ve hash testleri

AES-GCM round-trip, nondeterministic ciphertext, yanlış key, tamper detection, boş plaintext reddi ve kısa secret fail-fast davranışı test edildi. Telefon hash deterministik, pepper bağımlı ve geri çevrilemez olarak doğrulandı.

# 7. RBAC ve auth testleri

Owner/admin/sales_agent/viewer permission matrisi test edildi. Viewer phone reveal yapamıyor; sales_agent user/settings yetkisi alamıyor; manipüle rol stringleri yetki kazandırmıyor.

# 8. CSRF/session testleri

Login session oluşturuyor; yanlış parola ve pasif kullanıcı session üretmiyor. Logout artık `get_current_user` dependency’sinden geçtiği için CSRF gerektiriyor. Eksik/yanlış CSRF 403, doğru CSRF mutation için kabul edildi. Expired session Redis’ten silinip 401 dönüyor.

# 9. State machine testleri

Queued-preparing-dialing-ringing-answered-agent_active-completed zinciri ve terminal/invalid transition reddi test edildi. Aynı status’e geçiş no-op. Mevcut transition tablosunda `cancelled` yalnız `queued`, `preparing`, `dialing`, `ringing` için izinli; answered/agent_active sonrası cancel yok.

# 10. Call policy testleri

`LIVE_CALLS_ENABLED`, development allowlist, Istanbul saat sınırları, Pazar yasağı, günlük limit ve eşzamanlı limit test edildi. Global ve campaign limitleri ayrı doğrulandı.

# 11. Distributed lock testleri

Redis lock acquire/conflict/TTL, token sahipliği ve release hata logging davranışı test edildi. Release sırasında hata artık sessiz yutulmuyor; structured warning üretiyor.

# 12. Retry testleri

Busy, no-answer, voicemail gecikmeleri; max retry sınırı; wrong-number, do-not-call ve demo-requested için retry üretmeme; callback zamanının otomatik retry yerine kullanılması test edildi.

# 13. Lead import testleri

CSV, JSON ve XLSX import test edildi. Türkçe/İngilizce kolon eşleme, başlık satırı, boş satır atlama, invalid telefon raporu, eksik firma adı ve opsiyonel demo linki doğrulandı.

# 14. Duplicate lead testleri

Aynı `place_id`, aynı normalize telefon ve farklı formatlı aynı telefon duplicate sayılıyor. Eşzamanlı duplicate riskine karşı `phone_hash` için DB seviyesinde partial unique index eklendi.

# 15. Orchestrator testleri

Fake/no-enqueue akışla geçerli talebin `Call` oluşturduğu, policy reddinde call oluşmadığı, idempotency key’in duplicate üretmediği, aktif call varken ikinci talebin reddedildiği, suppression reddi ve telefonun yalnız `build_dial_info` aşamasında çözüldüğü test edildi.

# 16. Maliyet testleri

Audio/text cached/uncached token kalemleri, sıfır usage, eksik pricing, mini/premium model ayrımı, TRY->USD dönüşümü, Decimal hassasiyeti ve toplam maliyet test edildi.

# 17. API authorization testleri

Anonim protected endpoint 401, viewer mutation 403, owner lead listeleme ve phone reveal, reveal audit log, campaign create, suppression create, prompt activation ve live SSE auth kontrolü test edildi. Pricing update endpointi mevcut olmadığı için endpoint bazlı test yapılamadı.

# 18. Warning incelemesi

Kalan tek warning üçüncü taraf kaynaklıdır:

`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`

Alembic `path_separator` warning’i `alembic.ini` içine `path_separator = os` eklenerek giderildi. Warning filtrelenmedi.

# 19. Pytest sonucu

`uv run pytest -q` sonucu:

`96 passed, 1 warning in 9.64s`

# 20. Coverage sonucu

`uv run pytest --cov=app --cov-report=term-missing` sonucu:

`96 passed, 1 warning`, toplam coverage `%68`.

Kritik modül coverage:

- `app/core/crypto.py`: `%94`
- `app/core/rbac.py`: `%95`
- `app/core/security.py`: `%84`
- `app/services/importer.py`: `%89`
- `app/services/call_policy.py`: `%85`
- `app/services/call_service.py`: `%100`
- `app/services/orchestrator.py`: `%91`
- `app/services/cost_service.py`: `%95`

# 21. Ruff sonucu

`uv run ruff check app tests` sonucu:

`All checks passed!`

# 22. MyPy sonucu

`uv run mypy app` sonucu:

`Success: no issues found in 71 source files`

# 23. Migration doğrulaması

Komutlar geçti:

- `uv run alembic upgrade head`
- `uv run alembic downgrade base`
- `uv run alembic upgrade head`

Yeni revision: `20260717_0002_unique_lead_phone_hash.py`.

# 24. Docker config sonucu

`docker compose -f docker-compose.dev.yml config` geçti. Compose config PostgreSQL ve Redis servislerini doğruladı.

# 25. Bulunan gerçek backend hataları

- `logout` endpointi auth dependency kullanmadığı için CSRF kontrolünden geçmiyordu.
- Telefon normalizasyonu harf içeren bazı girişleri `phonenumbers` davranışına bırakıyordu.
- `encrypt_pii("")` boş plaintext kabul ediyordu.
- PII/hash secret değerleri kısa olduğunda fail-fast yoktu.
- Redis lock release hatası sessizce yutuluyordu.
- Lead duplicate kontrolünde `phone_hash` için DB seviyesinde unique constraint yoktu.
- Alembic config üçüncü taraf deprecation warning üretiyordu.

# 26. Yapılan minimum production düzeltmeleri

- `logout` artık `get_current_user` kullanıyor ve mutation CSRF kuralına uyuyor.
- `normalize_phone` harf içeren girişleri kontrollü reddediyor.
- `encrypt_pii` boş plaintext reddediyor.
- PII encryption key ve phone hash pepper için minimum uzunluk kontrolü eklendi.
- Redis lock release hatası warning olarak loglanıyor.
- `leads.phone_hash` için partial unique index eklendi.
- Alembic `path_separator = os` ile warning giderildi.

# 27. Başarısız veya ertelenen testler

Başarısız kalan zorunlu doğrulama yok. Pricing update endpointi mevcut olmadığı için endpoint authorization testi yapılamadı; RBAC ve mevcut API yüzeyi üzerinden doğrulandı.

# 28. Bilinen eksikler

- Toplam backend coverage `%68`; hedef yalnız kritik domain modülleri için sağlandı.
- `campaign_service`, task modülleri, provider adapter implementasyonları ve frontend/voice-agent dış kapsamda kaldı.
- Orchestrator concurrency testi gerçek paralel worker yarışı değil, idempotency/active-call/DB constraint tabanlı davranışı doğruluyor.
- Retry zamanı call window dışına düşerse otomatik pencereye kaydırma kuralı mevcut değil; mevcut davranış test edildi.

# 29. Sonraki önerilen aşama

Aşama 3 için öneri: campaign task/worker ve queue akışlarının test doubles ile sağlamlaştırılması; campaign lifecycle, queue dequeue, retry scheduling ve call task failure handling davranışlarının entegrasyon testleriyle kapatılması.

# 30. Git durumu

Repo hâlâ commit’siz ve dosyalar untracked görünüyor. `git status --short` kök proje dosyalarını `??` olarak listeliyor. Commit, push, reset, checkout, clean veya stash yapılmadı.
