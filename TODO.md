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
- [x] Frontend/panel aşamasına ayrı onayla geç
- [ ] (Kapsam dışı bırakıldı, ileride ele alınmalı) Codex ORTA-1/ORTA-2/ORTA-3 bulguları: end-call SpeechHandle bekleme, usage delivery hatasının completion reason'ı bozması, queue stop için explicit graceful timeout

## Aşama 5 — Next.js Yönetim Paneli (2026-07-18)

- [x] Backend route/schema envanterini çıkar (tahmin etmeden, dosyaları okuyarak)
- [x] Gerçek backend contract eksikliğini bul, doğrula, minimal düzelt: `app/api/routes/system.py` (dashboard/pricing/settings/audit-log)
- [x] Backend testlerini genişlet (118 → 129 passed), Ruff/MyPy temiz
- [x] `apps/web` scaffold (Next 15, React 19, Tailwind 4, TS strict)
- [x] Typed API client + Zod şemaları (tüm gerçek endpoint'ler için)
- [x] Auth/session/CSRF/RBAC (middleware + SessionProvider + PermissionGuard)
- [x] Tasarım sistemi + paylaşılan bileşenler
- [x] 20 sayfa (dashboard, leads, import, campaigns, calls+live, ops, content, system, users)
- [x] SSE canlı arama entegrasyonu (React Query invalidation deseniyle)
- [x] Vitest birim testleri (17 test)
- [x] Playwright E2E (11 test, gerçek backend'e karşı) — ilk çalıştırmada rate-limiter bulgusu bulundu ve testler `storageState` ile düzeltildi (backend zayıflatılmadı)
- [x] pnpm lint/typecheck/test/build kalite kapıları — hepsi temiz
- [x] `docs/frontend-management-panel.md` + `CLAUDE_PROGRESS_PHASE_5_FRONTEND.md`
- [ ] (Bilinçli eksik, sonraki oturum) Form alan-bazlı 422 hata haritalama her formda
- [ ] (Bilinçli eksik, sonraki oturum) Kalan ~4 E2E akışı (lead import, kampanya durum geçişi, arama başlatma/sonlandırma, suppression CRUD)
- [ ] (Bilinçli eksik, sonraki oturum) 320/768/1440px otomatik responsive testi
- [ ] Commit/push için kullanıcı onayı bekleniyor

## Aşama 5 — Codex Denetim Düzeltmesi (2026-07-18, `CLAUDE_FIX_PHASE_5_FRONTEND.md`)

- [x] `CODEX_AUDIT_PHASE_5_FRONTEND.md`'yi oku, YÜKSEK-1 (stale-cookie login loop) kök nedenini kodu okuyarak doğrula
- [x] `middleware.ts`: `/login`'den koşulsuz yönlendirme kaldırıldı
- [x] `app/login/page.tsx`: gerçek `useMe()` tabanlı self-redirect + `getSafeRedirectPath()` (open-redirect koruması)
- [x] `session-context.tsx`: defense-in-depth pathname guard
- [x] 9 yeni E2E testi (`auth-redirect.spec.ts`) + 5 yeni Vitest testi (`safe-redirect.test.ts`) — ek gerçek login POST'u olmadan (rate limiter etkilenmedi)
- [x] Playwright discovery sorununu doğrula (`cd apps/web && pnpm exec playwright test` gerçekten Vitest dosyalarını yüklemeye çalışıyordu)
- [x] `apps/web/playwright.config.ts` eklendi (gerçek config'i kopyalamadan, yeni bağımlılık eklemeden yol-düzeltmesi)
- [x] `apps/web/package.json`: `test:e2e`/`test:e2e:headed`/`test:e2e:list` script'leri
- [x] `pnpm exec playwright test --list` → yalnız 20 gerçek E2E testi (Vitest karışmıyor) doğrulandı
- [x] E2E gerçekten çalıştırıldı: 20/20 geçti (Codex'in koşamadığı senaryo)
- [x] Unit (22/22), lint, typecheck, build (apps/web + kök) — hepsi temiz
- [x] Backend regresyonu (dokunulmadı ama doğrulandı): 129 passed, değişmedi
- [x] Docker config (normal + voice) geçti
- [x] `CLAUDE_FIX_PHASE_5_FRONTEND.md` (29 bölüm) + `docs/frontend-management-panel.md`/`CLAUDE_PROGRESS_PHASE_5_FRONTEND.md`/`PROJECT_STATUS.md`/`CHANGELOG.md` düzeltme notlarıyla güncellendi
- [x] Karar: `FRONTEND COMMIT İÇİN HAZIR`
- [ ] Commit/push için kullanıcı onayı bekleniyor
- [ ] (Bu turun kapsamı dışında, kasıtlı olarak ertelendi) `CODEX_AUDIT_PHASE_5_FRONTEND.md` §26'daki ORTA/DÜŞÜK bulgular

## Aşama 5 — Frontend Kapanış Denetimi Düzeltmesi (2026-07-18, `CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md`)

- [x] `CODEX_FINAL_AUDIT_PHASE_5_FRONTEND.md`'yi oku, YÜKSEK-1 (`getSafeRedirectPath()` backslash open-redirect) kök nedenini doğrula (`new URL('/\evil.com', origin)` ile bağımsız yerel doğrulama)
- [x] `safe-redirect.ts`: ham+decode edilmiş değerde backslash/kontrol karakteri reddi, sınırlı (3 tur) percent-decode, `new URL()` + origin-eşitliği doğrulaması
- [x] Kullanım noktaları taranıp doğrulandı: yalnız `app/login/page.tsx`'in 2 çağrı noktası, ikisi de zaten helper üzerinden geçiyordu
- [x] 16 Vitest testi (`safe-redirect.test.ts`, 5'ten genişletildi) — backslash, çift-encode, kontrol karakteri, yanlış-pozitif kontrolü dahil
- [x] 3 yeni Playwright testi (`auth-redirect.spec.ts` 10d/10e/10f) — sıfır ek gerçek login POST'uyla
- [x] `pnpm exec playwright test --list` → 23 gerçek E2E testi (Vitest karışmıyor)
- [x] E2E gerçekten çalıştırıldı: 23/23 geçti
- [x] Unit (33/33), lint, typecheck, build (apps/web + kök) — hepsi temiz
- [x] Backend dokunulmadı (diff değişmedi)
- [x] `CLAUDE_FIX_PHASE_5_OPEN_REDIRECT.md` (20 bölüm) + `CLAUDE_FIX_PHASE_5_FRONTEND.md`/`docs/frontend-management-panel.md`/`PROJECT_STATUS.md`/`CHANGELOG.md` düzeltme notlarıyla güncellendi
- [x] Karar: `FRONTEND COMMIT İÇİN HAZIR`
- [ ] Commit/push için kullanıcı onayı bekleniyor
