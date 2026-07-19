#!/bin/sh
# Root olarak başlar (yalnız backup volume'ünün sahipliğini düzeltmek için),
# ardından gerçek komutu non-root `postgres` kullanıcısına (postgres:16-alpine
# image'ında zaten mevcut, uid 70) düşürüp çalıştırır — postgres/redis
# servislerinde de kullanılan aynı "root başlat, chown, düşür" deseni
# (bkz. CODEX_AUDIT_PHASE_6.md ORTA-3).
set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
mkdir -p "$BACKUP_DIR"
chown -R postgres:postgres "$BACKUP_DIR"

exec su-exec postgres "$@"
