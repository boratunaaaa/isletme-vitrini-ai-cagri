#!/usr/bin/env bash
# Bağımsız backup doğrulama: checksum + gzip bütünlüğü + içerik akıl sağlığı.
# Restore GEREKTİRMEZ — `postgres-backup.sh` sonunda örtük olarak zaten
# uygulanan kontrollerin AYNISINI, herhangi bir backup dosyası için manuel/
# periyodik olarak tekrar çalıştırmak için vardır (ör. cron ile günlük
# "geçmiş backup'lar hâlâ okunabilir mi" taraması).
#
# Kullanım: verify-backup.sh <backup-dosyası.sql.gz>
#           verify-backup.sh --all   (BACKUP_DIR altındaki TÜM backup'ları tarar)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

verify_one() {
	local file="$1"
	local checksum_file="${file}.sha256"
	local ok=true

	if [ ! -f "$file" ]; then
		log_error "[${file}] dosya bulunamadı."
		return 1
	fi

	if [ ! -f "$checksum_file" ]; then
		log_error "[${file}] checksum dosyası eksik (${checksum_file})."
		ok=false
	else
		local expected actual
		expected="$(cat "$checksum_file")"
		actual="$(sha256sum "$file" | awk '{print $1}')"
		if [ "$expected" != "$actual" ]; then
			log_error "[${file}] ÇEKSUM UYUŞMUYOR (beklenen=${expected} bulunan=${actual})."
			ok=false
		fi
	fi

	if ! gzip -t "$file" 2>/dev/null; then
		log_error "[${file}] gzip bütünlük kontrolü BAŞARISIZ."
		ok=false
	fi

	# NOT (CODEX_REAUDIT_PHASE_6.md YÜKSEK "backup false-fail regresyonu"):
	# bkz. `postgres-backup.sh`'deki aynı deseni açıklayan yorum — `pipefail`
	# yalnız bu tek pipeline için bilinçli olarak devre dışı bırakılır.
	set +o pipefail
	gzip -dc "$file" 2>/dev/null | head -c 4096 | grep -q "PostgreSQL database dump"
	content_check_status=$?
	set -o pipefail
	if [ "$content_check_status" -ne 0 ]; then
		log_error "[${file}] içerik pg_dump çıktısına benzemiyor."
		ok=false
	fi

	if [ "$ok" = "true" ]; then
		log_info "[${file}] GEÇERLİ (checksum + gzip + içerik doğrulandı)."
		return 0
	fi
	return 1
}

if [ "${1:-}" = "--all" ]; then
	BACKUP_DIR="${BACKUP_DIR:-/backups}"
	failures=0
	total=0
	while IFS= read -r f; do
		total=$((total + 1))
		if ! verify_one "$f"; then
			failures=$((failures + 1))
		fi
	done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'ivac-postgres-*.sql.gz' | sort)
	log_info "Toplam ${total} backup tarandı, ${failures} başarısız."
	[ "$failures" -eq 0 ]
else
	target="${1:?Kullanım: verify-backup.sh <backup-dosyası.sql.gz> | --all}"
	verify_one "$target"
fi
