# Pilot Runbook — İlk Gerçek Aramalar

Bu doküman, sistemin ilk kez GERÇEK bir telefon numarasını (kontrollü test numarası veya izinli bir pilot müşteri) aramasına izin verirken izlenecek adımları tanımlar. Bu depodaki HİÇBİR otomatik/AI oturumu bu adımları KENDİLİĞİNDEN gerçekleştirmez — hepsi insan operatör tarafından, elle, bilinçli onayla yapılır.

## Ön koşullar (bkz. [OPEN_OPERATIONAL_BLOCKERS.md](../OPEN_OPERATIONAL_BLOCKERS.md))

- [ ] Gerçek LiveKit projesi + SIP outbound trunk kurulu ve test edilmiş
- [ ] Gerçek OpenAI API key, yeterli kotayla
- [ ] Gerçek Netgsm hesabı, giden arama izni açık, trunk LiveKit'e bağlı
- [ ] Production domain + gerçek TLS sertifikası (bkz. [docs/production/DEPLOYMENT.md](production/DEPLOYMENT.md))
- [ ] Off-site backup en az bir kez BAŞARIYLA çalıştırılmış ve doğrulanmış
- [ ] KVKK/arama izni ve açıklama metni hazır (bu doküman hukuki onayı KAPSAMAZ — yalnız teknik adımları)

## 1. Pilot öncesi kontrol

```bash
make prod-health           # tüm servisler healthy mi
make doctor                # /ready + backup durumu tek komutta
make backup-status         # son başarılı backup ne zaman
```

`LIVE_CALLS_ENABLED` hâlâ `false` olmalı — bu adımda henüz açılmaz.

## 2. Pilot kullanıcı/hesap oluşturma

Panelden (`/users`) veya `make prod-bootstrap-admin` ile ilk owner hesabı zaten var olmalı. Pilot çağrıyı kimin başlatacağını belirleyin (owner veya `sales_agent` rolünde bir kullanıcı — `CALL_INITIATE` yetkisi gerekir).

## 3. Test numarası ekleme (ZORUNLU ilk adım)

`.env.production`'da `TEST_PHONE_ALLOWLIST` yalnız `APP_ENV != production` iken uygulanır — **production'da bu allowlist bypass edilir**. Bu yüzden gerçek production'da ilk arama, allowlist'e GÜVENMEDEN, doğrudan kontrollü bir numarayla (kendi telefonunuz veya ekip üyesi) yapılmalıdır.

## 4. Canlı arama açma

```bash
# .env.production'da:
LIVE_CALLS_ENABLED=true
```

Değişikliği uygulamak için:
```bash
docker compose -f compose.production.yml --env-file .env.production up -d --force-recreate api worker
```

## 5. İlk test çağrısı

1. Panelde bir lead açın (kendi/ekip test numaranızla, `phone` alanı gerçek numaranız).
2. "Ara" butonuna basın.
3. `make prod-logs service=worker` ile canlı takip edin — `place_call` task'ının alındığını, dispatch'in başladığını görün.
4. `make prod-logs service=voice-agent` ile agent'ın job'ı aldığını, SIP participant davet ettiğini izleyin.
5. Telefon çalmalı. Cevaplayın, kısa bir konuşma yapın (sistemin açılış cümlesini duyun, birkaç soru sorun).
6. Görüşmeyi doğal şekilde bitirin (agent'ın "end_call_safely" tool'unu tetiklemesini bekleyin veya panelden "Sonlandır"a basın).

## 6. Sonuç kontrolü

```bash
curl -s https://<DOMAIN>/api/calls/<call_id> -H "Cookie: ..." | jq
```

Kontrol edilecekler:
- [ ] `status` terminal bir değere ulaştı mı (`completed`/`answered` sonrası uygun outcome)
- [ ] `outcome` doğru mu (görüşmenin gerçek sonucuyla eşleşiyor mu)
- [ ] Transkript (varsa) makul mü, telefon numarası içermiyor mu
- [ ] `CallUsage` satırı gerçek bir maliyet tahmini içeriyor mu
- [ ] Panelde "Arama Geçmişi" sayfasında görünüyor mu

## 7. Log kontrolü

```bash
make prod-logs service=api | grep -i error
make prod-logs service=worker | grep -i error
make prod-logs service=voice-agent | grep -i error
```

Beklenmeyen hata/traceback varsa, telefon numarası/secret sızıp sızmadığını KONTROL EDİN (redaksiyon katmanları test edilmiş olsa da, ilk gerçek trafik her zaman ekstra dikkatle gözden geçirilmeli).

## 8. Hata durumunda dur (stop-on-error)

Aşağıdakilerden HERHANGİ biri olursa **derhal `LIVE_CALLS_ENABLED=false`'a geri dönün** ve devam etmeyin:
- Beklenmeyen/mükerrer arama (aynı numara birden fazla kez arandı)
- Sistemin görüşmede uygunsuz/yanlış bilgi vermesi
- Log'da düz metin telefon/secret görülmesi
- Çağrı sonucunun panelde YANLIŞ görünmesi

```bash
# .env.production'da LIVE_CALLS_ENABLED=false yapıp:
docker compose -f compose.production.yml --env-file .env.production up -d --force-recreate api worker
```

## 9. Geri alma (rollback)

Sorun kod kaynaklıysa: [docs/RELEASE_PROCESS.md](RELEASE_PROCESS.md) §Rollback'i izleyin. Veri bozulması varsa: [docs/production/BACKUP_AND_RESTORE.md](production/BACKUP_AND_RESTORE.md) restore prosedürünü izleyin — **önce yeni bir backup alın**, sonra restore edin.

## 10. Pilot sonrası backup

```bash
make backup
make backup-verify-all
```

Pilot çağrı(lar)ın sonuçlarını içeren backup'ın alındığını doğrulayın.

## 11. Kapanış

Pilotun sonuçlarını (kaç arama, kaç başarılı, ne öğrenildi) kısaca kaydedin. Genişletmeden önce (daha fazla numara, kampanya) [docs/GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md)'i tamamlayın.
