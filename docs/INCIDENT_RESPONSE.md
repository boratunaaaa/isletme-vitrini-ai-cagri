# Olay Müdahale Prosedürleri

Operasyonel gündelik sorun giderme için önce [docs/production/OPERATIONS_RUNBOOK.md](production/OPERATIONS_RUNBOOK.md)'a bakın — bu doküman daha CİDDİ, olay-seviyesi durumlar için hızlı karar ağaçlarını içerir.

## Genel ilk adımlar (her olayda)

1. `make doctor` — mevcut durumun anlık görüntüsü.
2. Etkiyi sınırlayın (aşağıdaki spesifik bölümlere bakın).
3. Zaman damgası + gözlemlenen semptomla kısa bir not tutun (post-mortem için).
4. Kritikse: kanal/iletişim yolunu bilgilendirin (bu depoda otomatik bir alerting hedefi TANIMLI DEĞİL — bkz. `OPEN_OPERATIONAL_BLOCKERS.md`, operatör elle takip etmelidir).

---

## 1. Dış servis kesintisi (LiveKit / OpenAI / Netgsm)

**Semptom**: `voice-agent` logunda tekrarlayan bağlantı hatası, `place_call` sürekli `dispatch_failed`.

- Sistem KENDİLİĞİNDEN güvenli davranır: `place_call` otomatik retry YAPMAZ (bilinçli tasarım — bkz. `PHASE_8_RESILIENCE_REPORT.md`), dial denemesi tek seferde temiz FAILED'e döner, gerçek bir "sonsuz retry" veya mükerrer arama riski YOKTUR.
- İlgili sağlayıcının status sayfasını kontrol edin.
- Kesinti geçene kadar `LIVE_CALLS_ENABLED=false` yaparak yeni deneme birikmesini durdurmayı düşünün.
- Kesinti bitince: `docker compose ... up -d --force-recreate voice-agent worker` (SDK'nın kendi reconnect/backoff mantığı zaten var, ama manuel restart daha hızlı olabilir).

## 2. PostgreSQL kesintisi

**Semptom**: `/ready` → `{"database": "..."}` not-ok, API 500'ler.

1. `docker compose ... logs postgres` — disk dolu mu, crash mi?
2. `df -h` (host) — disk alanı.
3. **ASLA** `docker compose down -v` denemeyin.
4. Container yeniden başlatılabiliyorsa: `docker compose ... restart postgres`, ardından `api`/`worker` bağlantı havuzunu otomatik yeniler (`pool_pre_ping=True`).
5. Veri kaybı şüphesi varsa → §7 (Restore).

## 3. Redis kesintisi

**Semptom**: login/CSRF/lock hataları, `/ready` → `redis: not ok`.

- **Kalıcı iş verisi kaybı riski YOKTUR** — Redis yalnız oturum/kilit/kuyruk/idempotency tutar (bkz. `docs/production/BACKUP_AND_RESTORE.md` §2).
- Etki: aktif kullanıcı oturumları düşer (yeniden giriş gerekir), o an kuyrukta bekleyen Celery job'ları kaybolabilir (watchdog_sweep, en fazla ~15dk içinde tutarsız DB durumlarını kendiliğinden temizler).
- `docker compose ... restart redis` — genellikle yeterlidir.
- Bir istek işlenirken lock alınamıyorsa (`LockBackendUnavailable`), API 503 döner (opak 500 DEĞİL) — bu beklenen, ayırt edilebilir davranıştır (bkz. `PHASE_8_RESILIENCE_REPORT.md`).

## 4. voice-agent çöküyor / crash-loop

**Semptom**: `docker compose ps` → voice-agent sürekli restart.

1. `docker compose ... logs voice-agent` — `configuration error: ...` mesajı mı, yoksa başka bir traceback mi?
2. `configuration error` ise: eksik/yanlış env değişkeni — production'da bu KASITLI fail-fast'tir (crash-loop DEĞİL, `restart: unless-stopped` normal üstel geri çekilmeyle dener), `.env.production`'ı düzeltip yeniden başlatın.
3. Başka bir traceback ise: hatayı izole edin, bu bir kod hatası olabilir — mevcut aktif çağrı YOKSA `voice-agent` restart edilebilir (yeni job'lar etkilenmez, yalnız o anki job kaybolur ve watchdog devreye girer).

## 5. Yanlış/istenmeyen arama

**Semptom**: sistem yanlış bir numarayı aradı VEYA aynı numarayı mükerrer aradı.

1. **Derhal** `LIVE_CALLS_ENABLED=false` yapın, `up -d --force-recreate api worker` ile uygulayın.
2. İlgili `Call` satırını ve `CallEvent` denetim izini inceleyin (`/api/calls/{id}`) — hangi kullanıcı/kampanya tetikledi?
3. Mükerrer aramaysa: bu, bilinen bir mükerrer-dispatch koruması OLAN bir alanla ilgilidir (`idempotency_seen`, bkz. `PHASE_8_RESILIENCE_REPORT.md`) — koruma neden çalışmadı sorusu kök-neden analizi gerektirir, ayrı bir oturumda ele alınmalı.
4. Etkilenen numarayı gerekirse suppression listesine (arama engeli) ekleyin.
5. Kök neden bulunup düzeltilmeden `LIVE_CALLS_ENABLED=true`'ya GERİ DÖNMEYİN.

## 6. Secret sızıntısı şüphesi

**Semptom**: log/rapor/ekran görüntüsünde düz metin bir token/parola/API key görüldü.

1. Şüpheli içeriği TERMİNALE/dokümana/harici bir araca YAPIŞTIRMADAN önce dikkatli olun.
2. Sızan secret'ı **DERHAL rotate edin** (`.env.production`'da değiştirip ilgili servisleri yeniden başlatın): `JWT_SECRET`/`COOKIE_SECRET`/`INTERNAL_SERVICE_TOKEN`/`LIVEKIT_API_SECRET`/`OPENAI_API_KEY` — rotasyon `INTERNAL_SERVICE_TOKEN` için hem `api` hem `voice-agent`'ta EŞ ZAMANLI yapılmalı (`INTERNAL_SERVICE_TOKEN_PREVIOUS` geçiş için kullanılabilir).
3. Sızıntı bir KOD hatasıysa (redaksiyon katmanını atlayan yeni bir log call-site): kök neden + regresyon testi ile düzeltilmeli (bkz. `PHASE_8_RESILIENCE_REPORT.md`'deki disiplin).
4. Sızıntı git geçmişine girdiyse: bu ciddi bir durumdur, history rewrite gerekebilir — kullanıcı onayı olmadan YAPILMAMALI.

## 7. PII log şüphesi (telefon/e-posta düz metin)

1. Etkiyi sınırlamak için ilgili servisi durdurun (`docker compose stop <servis>`).
2. Redaksiyon katmanları (`app/core/logging.py`, `agent/logging.py::RedactingFormatter`) zaten test edilmiştir (`PHASE_8_RESILIENCE_REPORT.md`) — buna rağmen sızıntı varsa bu YENİ bir kod hatasıdır, ayrı bir düzeltme oturumunda kök-neden+test ile ele alınmalı.
3. Log dosyalarında zaten yazılmış PII varsa, log saklama/silme politikanıza göre hareket edin.

## 8. Backup başarısız

- `journalctl -u ivac-postgres-backup.service -n 100` veya `make prod-logs service=backup`.
- Yaygın nedenler: disk dolu (script önceden algılayıp açık hata verir), Postgres erişilemez, `PGPASSWORD` yanlış.
- `make backup` ile elle yeniden deneyin.
- Ardışık 2+ başarısızlık: acil müdahale gerektirir (RPO risk altında).

## 9. Restore gerekiyor

[docs/production/BACKUP_AND_RESTORE.md](production/BACKUP_AND_RESTORE.md) §10'u izleyin. **ASLA** `--force` olmadan, **ASLA** checksum doğrulamadan restore çalıştırmayın. Restore öncesi mevcut (bozuk olsa bile) durumun bir yedeğini almayı düşünün.

## 10. Güvenli sistem kapatma

```bash
make prod-down     # volume'lara DOKUNMAZ, veriyi korur
```

Acil durumda TÜM stack'i durdurmak gerekiyorsa (ör. aktif bir güvenlik olayı) bu komut güvenlidir — yalnız container'ları durdurur.

---

## Post-mortem

Her ciddi olay sonrası kısaca kaydedin: ne oldu, ne zaman fark edildi, kök neden, alınan aksiyon, tekrarını önlemek için yapılan/yapılacak değişiklik.
