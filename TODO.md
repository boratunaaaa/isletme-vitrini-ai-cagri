# TODO.md

## Yapılacaklar

- [x] Klasör yapısını analiz et
- [x] Önemli projeleri belirle
- [x] Eksikleri çıkar
- [x] Aşama 4 voice-agent runtime iskeletini oluştur
- [x] Voice-agent Ruff, MyPy, Pytest ve coverage doğrulamalarını çalıştır
- [x] Backend regresyon testlerini çalıştır
- [x] Docker compose normal ve `voice` profile config doğrulamalarını çalıştır
- [x] `CLAUDE_AUDIT_PHASE_4.md` KRİTİK-1/KRİTİK-2/YÜKSEK-1..4 bulgularını düzelt (bkz. `CLAUDE_FIX_PHASE_4.md`)
- [x] Hatalı başarı testini (`test_job_handler_success_flow`) gerçek çok-turlu lifecycle testleriyle değiştir
- [x] Voice-agent Ruff/MyPy/Pytest/coverage doğrulamalarını düzeltme sonrası tekrar çalıştır (83 passed, %86)
- [x] Backend regresyonunu düzeltme sonrası tekrar çalıştır (111 passed, değişmedi)
- [x] `CODEX_AUDIT_PHASE_4_FIX.md`'nin 3 YÜKSEK bulgusunu düzelt (runtime error terminal, completion retry sınıflandırması, SIP backend status/outcome/retry taşıma) — bkz. `CLAUDE_FIX_PHASE_4_HIGH_FINDINGS.md`
- [x] Voice-agent testlerini genişlet (107 passed, %87 coverage)
- [x] Backend testlerini genişlet (118 passed, önceki 111 bozulmadı)
- [ ] Staging credential ve test numarası allowlist hazırlığını planla
- [ ] Gerçek LiveKit/OpenAI/SIP staging smoke test planını uygula
- [ ] Frontend/panel aşamasına ayrı onayla geç
- [ ] (Kapsam dışı bırakıldı, ileride ele alınmalı) Codex ORTA-1/ORTA-2/ORTA-3 bulguları: end-call SpeechHandle bekleme, usage delivery hatasının completion reason'ı bozması, queue stop için explicit graceful timeout
