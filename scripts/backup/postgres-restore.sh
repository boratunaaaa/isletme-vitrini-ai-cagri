#!/usr/bin/env bash
# PostgreSQL backup restore — GÜVENLİ MOD. Hedef veritabanı, checksum
# doğrulaması ve açık onay olmadan HİÇBİR ŞEY yapmaz. Parola yalnız
# PGPASSWORD ortam değişkeninden okunur (argümanda/`ps`'te görünmez).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

usage() {
	cat <<'EOF'
Kullanım:
  postgres-restore.sh --backup-file <path> --target-db <db_adı> --force [--drop-existing] [--allow-production-overwrite]

ZORUNLU:
  --backup-file <path>   Restore edilecek .sql.gz dosyası (yanında <path>.sha256 OLMALI)
  --target-db <db_adı>   Restore hedefi veritabanı adı
  --force                Açık onay bayrağı — bu OLMADAN script hiçbir DB işlemi yapmaz

OPSİYONEL:
  --drop-existing              Hedef veritabanı zaten varsa önce DROP eder
  --allow-production-overwrite Hedef, PGDATABASE (yapılandırılmış "production" DB adı) ile
                                AYNIYSA bu bayrak olmadan script REDDEDER. Bunu yalnız
                                gerçekten production'ı geri yüklemek istediğinizde kullanın.

Ortam değişkenleri: PGHOST, PGPORT, PGUSER, PGPASSWORD zorunludur (libpq standardı).
EOF
}

backup_file=""
target_db=""
force=false
drop_existing=false
allow_prod_overwrite=false

while [ $# -gt 0 ]; do
	case "$1" in
	--backup-file)
		backup_file="$2"
		shift 2
		;;
	--target-db)
		target_db="$2"
		shift 2
		;;
	--force)
		force=true
		shift
		;;
	--drop-existing)
		drop_existing=true
		shift
		;;
	--allow-production-overwrite)
		allow_prod_overwrite=true
		shift
		;;
	-h | --help)
		usage
		exit 0
		;;
	*)
		log_error "Bilinmeyen argüman: $1"
		usage
		exit 1
		;;
	esac
done

require_env PGHOST PGUSER PGPASSWORD

if [ -z "$backup_file" ] || [ -z "$target_db" ]; then
	log_error "--backup-file ve --target-db ZORUNLUDUR."
	usage
	exit 1
fi

# ── `target_db`, aşağıda hem SQL string literal'ı (`datname = '...'`) hem
#    quoted identifier (`"..."`) bağlamında kullanılıyor. Katı bir allowlist
#    olmadan quote/ayırıcı karakter içeren bir değer beklenmeyen SQL
#    çalıştırabilir (bkz. CODEX_AUDIT_PHASE_6.md YÜKSEK-2 — operatör
#    kontrollü input olsa da production restore'da kabul edilemez derecede
#    gevşekti). PostgreSQL'in kendi tanımlayıcı kurallarına göre kısıtlanır. ─
if ! printf '%s' "$target_db" | grep -qE '^[a-zA-Z_][a-zA-Z0-9_]{0,62}$'; then
	log_error "--target-db geçersiz: '${target_db}' — yalnız harf/rakam/alt çizgi, harf veya alt çizgiyle başlamalı, en fazla 63 karakter olmalı."
	exit 1
fi

if [ "$force" != "true" ]; then
	log_error "--force bayrağı olmadan restore YAPILMAZ (bu bilinçli bir güvenlik koruması)."
	exit 1
fi

if [ ! -f "$backup_file" ]; then
	log_error "Backup dosyası bulunamadı: ${backup_file}"
	exit 1
fi

checksum_file="${backup_file}.sha256"
if [ ! -f "$checksum_file" ]; then
	log_error "Checksum dosyası bulunamadı: ${checksum_file} — checksum'sız restore YAPILMAZ."
	exit 1
fi

# ── Checksum doğrulanmadan restore ASLA başlamaz ─────────────────────────
log_info "Checksum doğrulanıyor: ${checksum_file}"
expected_checksum="$(cat "$checksum_file")"
actual_checksum="$(sha256sum "$backup_file" | awk '{print $1}')"
if [ "$expected_checksum" != "$actual_checksum" ]; then
	log_error "ÇEKSUM UYUŞMUYOR — dosya bozulmuş veya değiştirilmiş olabilir. Restore İPTAL EDİLDİ."
	log_error "Beklenen: ${expected_checksum}"
	log_error "Bulunan:  ${actual_checksum}"
	exit 1
fi
log_info "Checksum doğrulandı."

if ! gzip -t "$backup_file" 2>/dev/null; then
	log_error "Backup dosyası gzip bütünlük kontrolünden geçemedi. Restore İPTAL EDİLDİ."
	exit 1
fi

# ── Production'ı yanlışlıkla ezme koruması ───────────────────────────────
if [ -n "${PGDATABASE:-}" ] && [ "$target_db" = "$PGDATABASE" ] && [ "$allow_prod_overwrite" != "true" ]; then
	log_error "HEDEF (${target_db}) yapılandırılmış PGDATABASE (production) İLE AYNI."
	log_error "Bunu gerçekten istiyorsanız --allow-production-overwrite bayrağını da ekleyin."
	log_error "Restore İPTAL EDİLDİ (bilinçli koruma — yanlışlıkla production restore'u engeller)."
	exit 1
fi

# ── Ne yapılacağını AÇIKÇA göster ────────────────────────────────────────
log_info "── Restore planı ──────────────────────────────────────────"
log_info "  Backup dosyası : ${backup_file}"
log_info "  Hedef veritabanı: ${target_db} (host: ${PGHOST})"
log_info "  --drop-existing : ${drop_existing}"
if [ "$drop_existing" = "true" ]; then
	log_info "  UYARI: '${target_db}' veritabanı ZATEN VARSA tamamen SİLİNECEK ve yeniden oluşturulacak."
fi
log_info "────────────────────────────────────────────────────────────"

# NOT (CODEX_REAUDIT_PHASE_6.md YÜKSEK-2 kalıntısı): `target_db` yukarıdaki
# katı allowlist (`^[a-zA-Z_][a-zA-Z0-9_]{0,62}$`) ile pratikte zaten
# injection'a KAPALI, ama önceki denetim "SQL içine interpolation yapma,
# dropdb/createdb argümanları kullan" beklentisini AÇIKÇA belirtmişti. Var
# olma kontrolü artık `psql -v` ile GÜVENLİ parametre bağlama kullanıyor
# (`:'target_db'` psql tarafından SQL string literal olarak escape edilir,
# elle string concat YOK); drop/create artık ham SQL metni yerine `dropdb`/
# `createdb` komut satırı araçlarının kendi (shell'e değil DB adına doğrudan
# argüman olarak geçen) arayüzünü kullanıyor — `--` ile DB adının bayrak
# olarak yorumlanması da engellenir.
db_exists() {
	psql --no-password -v target_db="$target_db" -tAc \
		"SELECT 1 FROM pg_database WHERE datname = :'target_db'" postgres 2>/dev/null | grep -q 1
}

if db_exists; then
	if [ "$drop_existing" = "true" ]; then
		log_info "Mevcut '${target_db}' siliniyor (--drop-existing)."
		dropdb --if-exists -- "$target_db"
	else
		log_error "'${target_db}' zaten mevcut ve --drop-existing verilmedi. Restore İPTAL EDİLDİ."
		exit 1
	fi
fi

log_info "'${target_db}' oluşturuluyor."
createdb -- "$target_db"

log_info "Restore başlıyor..."
if ! gzip -dc "$backup_file" | psql --no-password -v ON_ERROR_STOP=1 -d "$target_db" >/tmp/restore-output.log 2>&1; then
	log_error "Restore BAŞARISIZ oldu. Son satırlar:"
	tail -n 20 /tmp/restore-output.log >&2
	exit 1
fi

log_info "Restore tamamlandı: ${target_db}"
