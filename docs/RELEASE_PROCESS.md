# Release Süreci

## Versiyonlama

Bu repo şu an tek bir `main` dalı üzerinde, git commit SHA'sını sürüm kimliği olarak kullanıyor (ayrı bir semver etiketleme süreci henüz yok). Bir release hazırlarken:

```bash
git log --oneline -20          # neyin dahil olduğunu gözden geçirin
git tag -a v0.X.0 -m "..."     # opsiyonel: anlamlı bir etiket
```

## Release öncesi kontrol

```bash
make check                                      # backend: ruff+mypy+pytest
cd services/voice-agent && uv run ruff check agent tests && uv run mypy agent tests && uv run pytest
pnpm lint && pnpm typecheck && pnpm test && pnpm build
make prod-config                                # compose şema doğrulaması
```

Tümü geçmeden release ilerletilmemelidir. Detaylı kalite kapıları matrisi: [PHASE_14_FINAL_QUALITY_GATES.md](../PHASE_14_FINAL_QUALITY_GATES.md) (varsa) veya [FINAL_PROJECT_REPORT.md](../FINAL_PROJECT_REPORT.md).

## Build

```bash
make prod-build     # tüm production image'larını derle (--no-cache önerilir majör değişikliklerde)
```

`frontend` image'ı `API_URL` build-arg'ını BAKED-IN olarak alır — production domain değişmediyse yeniden build şart DEĞİLDİR, ama `.env.production`'daki `API_URL` değiştiyse (ör. domain değişikliği) frontend MUTLAKA yeniden build edilmelidir.

## Migration

```bash
make prod-migrate     # TEK, ayrı bir komut — asla api/worker başlangıcında otomatik çalışmaz
```

Migration'lar geri alınabilir olmalı (Alembic downgrade path'i her yeni migration'da düşünülmeli). Şema değişikliği geriye dönük UYUMSUZ ise (kolon silme/tip değişikliği), önce backward-compatible bir ara adım (expand-contract) planlanmalı.

## Deploy

```bash
docker compose -f compose.production.yml --env-file .env.production pull   # varsa registry'den
make prod-build                                                             # veya yerel build
make prod-migrate
docker compose -f compose.production.yml --env-file .env.production up -d --force-recreate api worker beat voice-agent frontend
```

`postgres`/`redis`/`caddy` genellikle her deploy'da yeniden oluşturulmaz (veri/sertifika kalıcılığı).

## Health kontrolü

```bash
make doctor          # container durumu + /ready + backup durumu
make prod-health
```

Tüm servisler `healthy` olmadan deploy TAMAMLANMIŞ sayılmaz.

## Smoke test

```bash
curl -I https://<DOMAIN>              # Caddy cevap veriyor mu
curl https://<DOMAIN>/health          # backend ayakta mı
curl https://<DOMAIN>/ready           # DB+Redis erişilebilir mi
```

Gerçek bir kullanıcı girişi (panelden) ve en az bir lead/çağrı listesi görüntüleme ile manuel doğrulama önerilir.

## Backup (deploy öncesi VE sonrası)

```bash
make backup    # deploy ÖNCESİ — şema değişikliği öncesi son durumu yakala
# ... deploy ...
make backup    # deploy SONRASI — yeni şemayla ilk backup
```

## Release notları

Her release için kısaca kaydedin: neler değişti (özellik/düzeltme/güvenlik), hangi migration'lar dahil, bilinen sınırlamalar. `CHANGELOG.md`'ye eklenmesi önerilir.

## Rollback

1. **Migration geri alınabilir mi?** Değilse, önce bir backup alın, sonra devam edin.
2. Kod: `git checkout <önceki-stabil-commit>`
3. `make prod-build`
4. Şema geri gitmesi gerekiyorsa: `docker compose ... run --rm migrate alembic downgrade <revizyon>` (yalnız backward-compatible ise; DEĞİLSE restore'a bkz. §4)
5. `docker compose -f compose.production.yml --env-file .env.production up -d --force-recreate ...`
6. `make doctor` ile doğrulayın.
7. Şema geri alınamıyorsa: [docs/production/BACKUP_AND_RESTORE.md](production/BACKUP_AND_RESTORE.md) restore prosedürünü izleyin (veri kaybı riski — yalnız son çare).

**Volume'lara asla `-v` ile dokunmayın** (`docker compose down -v` = TÜM veri kaybı).

## Deploy sıklığı / pencere

Bu proje için resmi bir "deploy penceresi" politikası tanımlı değil — küçük ekip/tek proje bağlamında, iş saatleri içinde, geri dönüş planı hazır olduğunda deploy edilmesi önerilir. Riskli değişiklikler (migration, secret rotasyonu) için düşük trafik saatleri tercih edilmelidir.
