# BASELINE_SECURITY_AUDIT.md

## 1. Yönetici özeti

2026-07-18 tarihinde ilk baseline commit öncesi repo salt-okunur güvenlik taramasından geçirildi. Secret, PII/lead verisi, cache/build/log/transcript/ses/model dosyaları ve büyük dosyalar commit kapsamı açısından kontrol edildi. `.gitignore` güvenli desenlerle genişletildi ve kaynak kodu yanlışlıkla dışarıda bırakan `/models/` kapsamı düzeltildi.

Son doğrulamada voice-agent Ruff, MyPy ve 107 testten geçti. Backend Ruff, MyPy ve 118 testten geçti. Docker Compose `config` çıktıları default ve `voice` profili için geçerli.

## 2. Başlangıç Git durumu

- Repo kökü: `/Users/kadirugur/Projects/isletme-vitrini-ai-cagri`
- Aktif branch: `main`
- Commit geçmişi: boş, baseline commit henüz yoktu.
- Remote: tanımlı değil.
- Başlangıçta proje dosyalarının tamamı untracked görünüyordu.
- Repo dışı dosyalar commit kapsamına alınmadı.

## 3. İncelenen dosya kapsamı

Commit adayı kapsamı kaynak kod, testler, migration dosyaları, Docker/Compose yapılandırması, dokümantasyon, lock dosyaları, manifestler, örnek environment dosyası ve denetim/ilerleme raporlarından oluştu.

Ignore edilen alanlar ayrıca kontrol edildi: `.venv`, Python cache dizinleri, test cache dizinleri, coverage çıktıları, OS dosyaları, log/ses/transcript/model/cache/data/backups alanları.

## 4. `.gitignore` doğrulaması

Doğrulanan ve/veya eklenen kapsam:

- `.env`, `.env.*`, `!.env.example`
- `node_modules/`, `.next/`, `dist/`, `build/`, `coverage/`, `htmlcov/`
- `.venv/`, `venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `*.log`, `logs/`
- `*.wav`, `*.mp3`, `*.m4a`, `*.ogg`, `*.webm`, `recordings/`, `transcripts/`
- `*.db`, `*.sqlite`, `*.sqlite3`, `*.dump`, `*.sql.gz`
- `.huggingface/`, `.cache/`, `/models/`, `/model-cache/`
- `.DS_Store`, `.idea/`, `.vscode/`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa*`, `id_ed25519*`
- `*.tfstate`, `*.tfstate.*`, `.terraform/`

Önemli düzeltme: `models/` deseni `services/api/app/models/` kaynak kodunu da ignore ediyordu. Desen `/models/` olarak daraltıldı. `uv.lock` ve olası `pnpm-lock.yaml` dosyaları ignore edilmedi.

## 5. Secret taraması

`rg` ile commit adaylarında aşağıdaki kavramlar ve benzerleri arandı: OpenAI key, Bearer token, LiveKit secret, Netgsm password, internal service token, JWT/cookie/PII key, phone hash pepper, database URL, private key, access token, API key, password.

Sonuç:

- Gerçek secret bulunmadı.
- `.env.example` içindeki secret alanları boş placeholder olarak doğrulandı.
- Testlerde ve raporlarda sahte/repro token örnekleri bulundu; gerçek credential görünümünde değerlendirilmedi.
- `DATABASE_URL` ve `DATABASE_URL_TEST` yalnız lokal geliştirme placeholder değerleri içeriyor.
- `gitleaks` sistemde kurulu değildi; yeni paket kurulmadı.

## 6. PII ve lead veri taraması

Telefon, email, fixture veri dosyaları, CSV/JSON/XLSX benzeri dosyalar ve transcript/ses kayıtları arandı.

Sonuç:

- Gerçek lead, müşteri listesi, transcript veya ses kaydı bulunmadı.
- `services/api/tests/fixtures/leads_tr.csv` ve `services/api/tests/fixtures/leads_en.json` test fixture dosyalarıdır; içerikleri sentetik işletme ve telefon örneklerinden oluşur.
- Test/dokümantasyon içinde telefon ve email örnekleri bulundu; bağlamları test/repro amaçlıdır.
- `recordings/` ve `transcripts/` ignore kapsamındadır.

Kalan düşük risk: Bazı test telefonları gerçek formatta yazılmış sentetik örneklerdir. Staging öncesi şart değildir, ancak ileride `+905550000000` benzeri açık rezerv test formatına taşınması daha temiz olur.

## 7. Hard-code credential denetimi

Kaynak kodda hard-code OpenAI key, LiveKit secret, Netgsm SIP password, internal token, production DB URL, caller ID veya transfer numarası bulunmadı.

Development defaultları boş veya lokal placeholder değerleridir. Production kritik ayarlarda fail-fast davranışı önceki Aşama 4 denetimlerinde doğrulanmıştır.

## 8. Büyük dosya denetimi

5 MB üzeri commit adayı dosya bulunmadı.

Büyük dosyalar yalnız ignore edilen `.venv` ve cache alanlarında görüldü; bunlar commit kapsamına alınmadı.

## 9. Cache/build/log/transcript denetimi

`git status --ignored --short` ile ignore edilen dosyalar kontrol edildi. Aşağıdakiler commit dışında bırakıldı:

- `.DS_Store`
- `.coverage`
- `.mypy_cache/`
- `.pytest_cache/`
- `.ruff_cache/`
- `.venv/`
- `__pycache__/`
- `packages/` ve kök `tests/` altındaki yalnız `.DS_Store` kalıntıları

Log, gerçek transcript, ses kaydı, local DB dump, SQLite dosyası veya model artifact commit adayı olarak bulunmadı.

## 10. Rapor dosyalarının kontrolü

Aşağıdaki raporların commit kapsamına alınması planlandı ve secret/PII açısından kontrol edildi:

- `CODEX_AUDIT.md`
- `CODEX_PROGRESS_PHASE_1.md`
- `CODEX_PROGRESS_PHASE_2.md`
- `CODEX_PROGRESS_PHASE_3.md`
- `CLAUDE_PROGRESS_PHASE_4.md`
- `CLAUDE_AUDIT_PHASE_4.md`
- `CLAUDE_FIX_PHASE_4.md`
- `CODEX_AUDIT_PHASE_4_FIX.md`
- `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`
- `CODEX_FINAL_AUDIT_PHASE_4.md`
- `PROJECT_STATUS.md`
- `TODO.md`
- `CHANGELOG.md`
- `BASELINE_SECURITY_AUDIT.md`

Raporlarda önceki denetimlere ait sahte/repro token ve telefon örnekleri bulunuyor; gerçek secret veya gerçek lead verisi olarak değerlendirilmedi.

## 11. Üretim kodunda yapılan düzeltmeler

Üretim kodu değiştirilmedi.

Yalnız `.gitignore` düzeltildi:

- Güvenlik ve artifact desenleri genişletildi.
- `models/` deseni `/models/` olarak daraltılarak `services/api/app/models/` kaynak kodunun commit dışında kalması engellendi.

## 12. Test sonuçları

Voice-agent:

- `uv run ruff check agent tests`: geçti.
- `uv run mypy agent`: geçti.
- `uv run pytest -q`: 107 passed.

Backend:

- `uv run ruff check app tests`: geçti.
- `uv run mypy app`: geçti.
- İlk sandbox içi `uv run pytest -q` denemesi `localhost:5432` test DB bağlantısı sandbox tarafından engellendiği için başarısız oldu.
- Dış sandbox yetkisiyle aynı backend pytest komutu tekrarlandı: 118 passed, 1 üçüncü taraf warning.

## 13. Docker config sonuçları

- `docker compose -f docker-compose.dev.yml config`: geçti.
- `docker compose -f docker-compose.dev.yml --profile voice config`: geçti.
- Docker servisi başlatılmadı.

## 14. Stage edilen dosya sayısı ve kapsamı

Bu rapor yazılırken commit adayı dosya sayısı 173 idi; bu raporun eklenmesiyle stage kapsamının 174 dosya olması beklenir.

Kapsam:

- Backend kaynak kodu, migrationlar ve testler
- Voice-agent kaynak kodu, testleri ve lock dosyası
- Dockerfile ve development compose
- Dokümantasyon, karar/ilerleme/denetim raporları
- Manifest ve workspace yapılandırması
- `.env.example`

## 15. Commit dışı bırakılan dosyalar

Commit dışında bırakılan başlıca dosya/dizin türleri:

- `.env` ve gerçek secret dosyaları
- `.venv/`
- Cache dizinleri
- Coverage çıktıları
- `.DS_Store`
- Loglar
- Ses kayıtları
- Transcript dosyaları
- Local DB/dump dosyaları
- Model/cache artifactleri
- Terraform/OpenTofu state dosyaları

Repo dışı `~/AI_MEMORY/**` dosyaları okunmuş, değiştirilmemiş ve commit kapsamına alınmamıştır. `~/AI_MEMORY/GLOBAL_STATUS.md` eski Aşama 4 test sayısını taşıyor; manuel güncelleme gerekir.

## 16. Baseline commit bilgisi

Planlanan commit mesajı:

```text
feat: establish tested AI call center baseline
```

Planlanan commit body:

```text
- add tested FastAPI backend and domain services
- add internal voice-agent API contract
- add LiveKit and OpenAI Realtime voice runtime
- add SIP terminal handling and campaign retry integration
- add backend and voice-agent test suites
- add Docker development configuration and technical documentation
```

Bu rapor commit öncesinde oluşturulduğu için kesin commit hash'i commit sonrası doğrulamada raporlanacaktır.

## 17. Commit sonrası Git durumu

Bu rapor commit öncesinde oluşturuldu. Commit sonrası `git status --short`, `git log -1 --oneline` ve `git show --stat --oneline --summary HEAD` ile doğrulama yapılacaktır.

## 18. Push durumu

Push yapılmayacak. Remote tanımlı değildir.

## 19. Kalan riskler

- Gerçek OpenAI, LiveKit, Netgsm ve telefon çağrısı staging credential olmadan doğrulanmadı; bu bilinçli olarak kapsam dışıydı.
- Backend testleri lokal PostgreSQL test veritabanına ihtiyaç duyuyor; sandbox içinde doğrudan bağlantı engellendi, dış sandbox yetkisiyle doğrulandı.
- Test fixture telefonları sentetik olsa da gerçek formatta. İleride daha belirgin rezerv test numaralarına taşınması önerilir.
- `~/AI_MEMORY/GLOBAL_STATUS.md` eski Aşama 4 özetini taşıyor ve repo dışında olduğu için güncellenmedi.

## 20. Sonraki önerilen aşama

İlk baseline commit sonrası push yapılmadan önce kullanıcıdan açık onay alınmalı. Sonraki teknik aşama, gerçek secretları repoya yazmadan staging ortamında kontrollü credential hazırlığı ve allowlist test numarasıyla ilk canlı entegrasyon doğrulamasıdır.
