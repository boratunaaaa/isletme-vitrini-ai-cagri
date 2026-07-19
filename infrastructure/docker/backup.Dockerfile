# Backup aracı imajı: `pg_dump`/`pg_restore` (postgres:16-alpine tabanı ile
# SUNUCU sürümüyle birebir eşleşir) + `restic` (off-site şifreli backup) +
# bash. Bu imaj `compose.production.yml`'de yalnız `profiles: ["tools"]`
# altında tanımlıdır — `up -d` ile OTOMATİK BAŞLAMAZ, yalnız host systemd
# timer'ı `docker compose run --rm backup <script>` ile tetikler.
FROM postgres:16-alpine

RUN apk add --no-cache bash restic ca-certificates tzdata coreutils

WORKDIR /scripts
COPY scripts/backup/postgres-backup.sh /scripts/postgres-backup.sh
COPY scripts/backup/postgres-restore.sh /scripts/postgres-restore.sh
COPY scripts/backup/verify-backup.sh /scripts/verify-backup.sh
COPY scripts/backup/restore-smoke-test.sh /scripts/restore-smoke-test.sh
COPY scripts/backup/offsite-backup.sh /scripts/offsite-backup.sh
COPY scripts/backup/lib.sh /scripts/lib.sh
COPY scripts/backup/entrypoint.sh /scripts/entrypoint.sh
RUN chmod +x /scripts/*.sh

# NOT (CODEX_AUDIT_PHASE_6.md ORTA-3): önceden non-root USER YOKTU. Container
# root olarak BAŞLAR (yalnız `/backups` volume'ünün sahipliğini düzeltmek
# için) ve `entrypoint.sh` gerçek komutu her zaman `postgres` kullanıcısına
# (su-exec ile) düşürür — bu image'da her zaman root olarak ÇALIŞMAZ.
ENTRYPOINT ["/scripts/entrypoint.sh"]
CMD ["/scripts/postgres-backup.sh"]
