#!/usr/bin/env bash
# Disposable restore tatbikatı — GERÇEK production verisi/credential
# KULLANMAZ. Tamamen izole, rastgele adlı, tek kullanımlık iki veritabanı
# (`ivac_smoke_src_*` kaynak, `ivac_smoke_dst_*` hedef) üzerinde çalışır ve
# sonunda ikisini de siler. `postgres-backup.sh` ile AYNI sıkıştırma/
# checksum sözleşmesini, `postgres-restore.sh`'i GERÇEKTEN çağırarak test
# eder (mantığı yeniden yazmaz).
#
# Adımlar (PRODUCTION_INFRA_REPORT.md §9 ile birebir):
#   1) küçük güvenli test verisi oluştur
#   2) backup al
#   3) yeni disposable database oluştur
#   4) backup'ı restore et
#   5) beklenen tablo/veri geldiğini doğrula
#   6) checksum bozukken restore'un reddedildiğini doğrula
#   7) sonuçları raporla
#   8) test ortamını temizle
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

require_env PGHOST PGUSER PGPASSWORD

suffix="$(date -u +%Y%m%d%H%M%S)$$"
src_db="ivac_smoke_src_${suffix}"
dst_db="ivac_smoke_dst_${suffix}"
work_dir="$(mktemp -d)"
backup_file="${work_dir}/smoke-${suffix}.sql.gz"

failures=0
step() { log_info "── Adım: $* ─────────────────────────────────────"; }
check() {
	# check <açıklama> <komut...>
	local desc="$1"
	shift
	if "$@"; then
		log_info "PASS: ${desc}"
	else
		log_error "FAIL: ${desc}"
		failures=$((failures + 1))
	fi
}

cleanup() {
	step "Temizlik"
	psql --no-password -tAc "DROP DATABASE IF EXISTS \"${dst_db}\";" postgres >/dev/null 2>&1 || true
	psql --no-password -tAc "DROP DATABASE IF EXISTS \"${src_db}\";" postgres >/dev/null 2>&1 || true
	rm -rf "$work_dir"
	log_info "Disposable veritabanları ve geçici dosyalar silindi."
}
trap cleanup EXIT

# ── 1) Küçük, güvenli test verisi ────────────────────────────────────────
step "1) Test kaynak veritabanı + küçük test verisi oluştur"
psql --no-password -c "CREATE DATABASE \"${src_db}\";" postgres
psql --no-password -d "$src_db" -c "
  CREATE TABLE smoke_test (id serial PRIMARY KEY, label text NOT NULL);
  INSERT INTO smoke_test (label) VALUES ('restore-drill-a'), ('restore-drill-b');
"
row_count_before="$(psql --no-password -tAc "SELECT count(*) FROM smoke_test;" "$src_db")"
log_info "Kaynakta ${row_count_before} satır oluşturuldu."

# ── 2) Backup al (gerçek backup.sh ile AYNI komut/format, ayrı hedef dizinde) ─
step "2) Backup al"
PGDATABASE="$src_db" pg_dump --no-password --format=plain --no-owner --no-privileges \
	| gzip -9 >"$backup_file"
sha256sum "$backup_file" | awk '{print $1}' >"${backup_file}.sha256"
check "backup dosyası oluşturuldu ve boş değil" test -s "$backup_file"
check "backup dosyası verify-backup.sh'ten geçiyor" "${SCRIPT_DIR}/verify-backup.sh" "$backup_file"

# ── 3+4) Yeni disposable database + gerçek restore script'iyle restore ──
step "3-4) Disposable hedefe gerçek postgres-restore.sh ile restore et"
if "${SCRIPT_DIR}/postgres-restore.sh" --backup-file "$backup_file" --target-db "$dst_db" --force; then
	log_info "PASS: restore script'i başarıyla tamamlandı"
else
	log_error "FAIL: restore script'i başarısız oldu"
	failures=$((failures + 1))
fi

# ── 5) Beklenen veri geldi mi? ────────────────────────────────────────────
step "5) Restore edilen veriyi doğrula"
row_count_after="$(psql --no-password -tAc "SELECT count(*) FROM smoke_test;" "$dst_db" 2>/dev/null || echo "ERROR")"
check "restore edilen satır sayısı kaynakla eşleşiyor (${row_count_before})" \
	test "$row_count_after" = "$row_count_before"
label_check="$(psql --no-password -tAc "SELECT label FROM smoke_test ORDER BY id LIMIT 1;" "$dst_db" 2>/dev/null || echo "ERROR")"
check "beklenen satır içeriği doğru ('restore-drill-a')" test "$label_check" = "restore-drill-a"

# ── 6) Bozuk checksum reddediliyor mu? ────────────────────────────────────
step "6) Bozuk checksum ile restore'un REDDEDİLDİĞİNİ doğrula"
bad_target="ivac_smoke_reject_${suffix}"
echo "0000000000000000000000000000000000000000000000000000000000000000" >"${backup_file}.sha256.bak"
cp "${backup_file}.sha256" "${backup_file}.sha256.orig"
cp "${backup_file}.sha256.bak" "${backup_file}.sha256"
if "${SCRIPT_DIR}/postgres-restore.sh" --backup-file "$backup_file" --target-db "$bad_target" --force >/tmp/smoke-reject.log 2>&1; then
	log_error "FAIL: bozuk checksum'a rağmen restore ÇALIŞTI (beklenmiyordu)"
	failures=$((failures + 1))
	psql --no-password -tAc "DROP DATABASE IF EXISTS \"${bad_target}\";" postgres >/dev/null 2>&1 || true
else
	log_info "PASS: bozuk checksum ile restore doğru şekilde reddedildi"
fi
cp "${backup_file}.sha256.orig" "${backup_file}.sha256"
rm -f "${backup_file}.sha256.bak" "${backup_file}.sha256.orig"

# ── 7) Rapor ───────────────────────────────────────────────────────────
step "7) Sonuç"
if [ "$failures" -eq 0 ]; then
	log_info "RESTORE SMOKE TEST: TÜMÜ GEÇTİ (0 başarısızlık)."
	exit 0
else
	log_error "RESTORE SMOKE TEST: ${failures} kontrol BAŞARISIZ."
	exit 1
fi
