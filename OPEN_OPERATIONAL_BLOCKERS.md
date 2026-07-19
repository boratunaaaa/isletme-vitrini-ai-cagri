# Açık Operasyonel Engeller — Gerçek Production'a Geçmeden Önce

Bu liste, **kod tarafında tamamlanmış** olan ama gerçek production kullanımı için kullanıcının (Kadir) yapması gereken, bu AI oturumlarının hiçbirinde yapılamayan/yapılmayan DIŞ işleri kapsar. Hiçbiri kod değişikliği değildir — hepsi gerçek hesap/credential/altyapı/onay gerektirir.

## 1. Gerçek LiveKit projesi ve SIP trunk

- LiveKit Cloud'da (veya self-hosted) gerçek bir proje oluşturulmalı.
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` alınmalı.
- SIP outbound trunk LiveKit konsolunda oluşturulmalı, `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` alınmalı.
- **Bu depoda hiç denenmedi** — yalnız sahte/geçersiz bir `LIVEKIT_URL` ile dispatch'in TEMİZ ŞEKİLDE başarısız olduğu doğrulandı (`PHASE_11_E2E_REPORT.md`).

## 2. Gerçek OpenAI API key

- Yeterli kota/limitli bir OpenAI API key alınmalı.
- Realtime API erişiminin hesapta AÇIK olduğu doğrulanmalı.
- **Bu depoda hiç gerçek bir OpenAI Realtime bağlantısı kurulmadı.**

## 3. Netgsm SIP trunk + izinler

- Gerçek bir Netgsm hesabı, giden arama iznine SAHİP olmalı.
- SIP trunk bilgileri LiveKit'e (yukarıdaki #1) doğru şekilde bağlanmalı.
- **Bu depoda hiç gerçek bir Netgsm bağlantısı denenmedi.**

## 4. Numara tahsisi ve arama izinleri

- Hangi numaraların aranacağı, giden numara gösterimi (caller ID) politikası netleştirilmeli.
- Bu, iş/hukuk kararıdır, bu depoda ele alınmadı.

## 5. Production domain ve DNS

- Gerçek bir domain DNS kaydı production sunucu IP'sine işaret etmeli.
- **Bu depoda yalnız `localhost` üzerinden yerel Caddy override'ı ile test edildi** (`deploy/caddy/Caddyfile.local`) — gerçek bir domain hiç kullanılmadı.

## 6. Gerçek ACME/TLS sertifikası

- Caddy, gerçek domain ile Let's Encrypt'ten otomatik sertifika alacak — bu yalnız gerçek DNS+80/443 erişimiyle çalışır.
- **Bu depoda hiç denenmedi** (`tls internal` ile self-signed test edildi, gerçek ACME akışı DEĞİL).

## 7. Production sunucu

- Yeterli kaynaklı (bu depodaki disposable test ortamı yalnız 2.9GB RAM'li kısıtlı bir geliştirme VM'inde çalıştı — gerçek production sunucusu bundan daha güçlü olmalı) bir sunucu/VM sağlanmalı.
- Güvenlik duvarı: yalnız 80/443 açık.

## 8. Off-site backup deposu (S3/restic)

- Gerçek bir S3 (veya restic destekli başka bir) depo oluşturulmalı.
- `RESTIC_REPOSITORY`, `RESTIC_PASSWORD`, (S3 ise) `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` alınmalı.
- **Bu depoda yalnız local/disposable backup+restore test edildi** (`PHASE_11_E2E_REPORT.md` §2, adım 19-21 — TÜMÜ GEÇTİ ama gerçek off-site depo KULLANILMADI).

## 9. Gerçek off-site backup başarısı

- Yukarıdaki #8 kurulduktan sonra, en az bir gerçek off-site backup BAŞARIYLA tamamlanmalı ve doğrulanmalı.

## 10. Gerçek uzak restore tatbikatı

- Off-site depodan gerçek bir restore denenmeli ve süresi ölçülmeli (RTO/RPO doğrulaması).
- **Bu depoda yalnız local disposable restore test edildi.**

## 11. Alerting hedefi

- Bu depoda dahili bir alerting/notification sistemi YOK (bilinçli — "ağır telemetri platformu eklenmeyecek" kısıtı, bkz. `PHASE_10_OPERATIONS_REPORT.md`).
- Servis unhealthy/backup başarısız durumlarında bir insanın haberdar olacağı bir mekanizma (email/Slack/SMS/PagerDuty vb.) kullanıcı tarafından ayrıca kurulmalı.

## 12. Gerçek pilot çağrı

- Yukarıdaki #1-4 tamamlandıktan sonra, [docs/PILOT_RUNBOOK.md](docs/PILOT_RUNBOOK.md) izlenerek en az bir gerçek, kontrollü test numarasına arama yapılmalı.
- **Bu depoda hiç gerçek arama yapılmadı** — bu, tüm oturumların açık, tekrarlanan bir güvenlik kısıtıydı.

## 13. Hukuki/operasyonel onaylar

- KVKK uyumluluğu, arama izni/açıklama metni, olası kayıt (recording) izinleri — bunlar TEKNİK bir AI oturumunun karar veremeyeceği konulardır, ilgili hukuki danışmanlıkla netleştirilmeli.
- Marka/pazarlama onayı (sistemin müşteriyle nasıl konuşacağı, script içeriği) iş sahibi tarafından son kez gözden geçirilmeli.

---

**Özet**: Kod/altyapı/test tarafı (backend, frontend, voice-agent, Docker, backup/restore mekanizması, güvenlik kontrolleri, gözlemlenebilirlik) bu oturumlar boyunca kapsamlı biçimde inşa edildi ve test edildi (bkz. `FINAL_PROJECT_REPORT.md`). Yukarıdaki 13 madde ise gerçek dış hesap/credential/onay gerektirdiği için hiçbir AI oturumunda yapılamadı ve yapılmamalıydı — bunlar kullanıcının kendisinin tamamlaması gereken adımlardır.
