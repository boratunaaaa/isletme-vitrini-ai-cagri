#!/usr/bin/env bash
# PostgreSQL production backup: tutarlı pg_dump + sıkıştırma + checksum +
# atomik yazım + retention. `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD`/
# `PGDATABASE` libpq'nun standart ortam değişkenleridir (pg_dump bunları
# otomatik okur — parola hiçbir argümanda/loglama satırında görünmez).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

require_env PGHOST PGUSER PGDATABASE PGPASSWORD

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
LOCK_FILE="${BACKUP_DIR}/.postgres-backup.lock"

mkdir -p "$BACKUP_DIR"

# ── Eşzamanlı ikinci backup'ı engelle (flock, host/container restart'a
#    dayanıklı — lock dosyası backup volume'ünde, process ölünce flock
#    otomatik serbest kalır) ──────────────────────────────────────────────
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
	log_error "Başka bir backup zaten çalışıyor (lock: ${LOCK_FILE}). Çıkılıyor."
	exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
filename="ivac-postgres-${timestamp}.sql.gz"
tmp_path="${BACKUP_DIR}/.tmp.${filename}"
final_path="${BACKUP_DIR}/${filename}"
checksum_path="${final_path}.sha256"

log_info "Backup başlıyor: db=${PGDATABASE} host=${PGHOST} -> ${filename}"

# ── Disk doluluğu ön kontrolü (görünür raporlama için) ───────────────────
available_kb="$(df -Pk "$BACKUP_DIR" | awk 'NR==2 {print $4}')"
if [ "${available_kb:-0}" -lt 51200 ]; then
	log_error "Disk alanı kritik seviyede düşük (${available_kb} KB, ${BACKUP_DIR}). Backup denenmiyor."
	exit 1
fi

cleanup_tmp() {
	rm -f "$tmp_path"
}
trap cleanup_tmp ERR

# ── pg_dump | gzip: `set -o pipefail` sayesinde pg_dump başarısızlığı da
#    yakalanır (yalnız gzip'in exit kodu değil). --no-password: parola
#    interaktif sorulmaz, yalnız PGPASSWORD ortam değişkeninden okunur. ──
if ! pg_dump --no-password --format=plain --no-owner --no-privileges | gzip -9 >"$tmp_path"; then
	log_error "pg_dump/gzip başarısız oldu — yarım kalan dosya silindi, backup BAŞARISIZ."
	exit 1
fi

if [ ! -s "$tmp_path" ]; then
	log_error "Backup dosyası boş üretildi — backup BAŞARISIZ."
	exit 1
fi

if ! gzip -t "$tmp_path" 2>/dev/null; then
	log_error "Backup gzip bütünlük kontrolünden geçemedi — backup BAŞARISIZ."
	exit 1
fi

# İçerik akıl sağlığı kontrolü: gerçek bir pg_dump çıktısı mı?
# NOT (CODEX_REAUDIT_PHASE_6.md YÜKSEK "backup false-fail regresyonu"):
# `gzip -dc | head -c N | grep -q ...` altında `set -o pipefail` AKTİFKEN,
# `head -c N` N byte okuyup pipe'ı kapattığında, henüz N byte'tan fazla veri
# yazmaya çalışan `gzip -dc` SIGPIPE alıp exit 141 ile sonlanıyordu — `grep -q`
# eşleşmeyi BULMUŞ olsa bile pipefail pipeline'ı BAŞARISIZ sayıyordu. Gerçek
# boyuttaki (birkaç KB'tan büyük) her dump için bu NEREDEYSE KESİN
# tetikleniyordu (100 disposable tekrarda 100/100 doğrulandı) — küçük test
# dump'larında "aralıklı" görünmesi yalnızca dump boyutunun bazen 4096
# byte'ın altında kalmasındandı. Yalnız `grep`in gerçek sonucunu önemsediğimiz
# için `pipefail` bilinçli olarak SADECE bu tek pipeline için devre dışı
# bırakılır (script'in geri kalanında `pipefail` aktif kalır).
set +o pipefail
gzip -dc "$tmp_path" 2>/dev/null | head -c 4096 | grep -q "PostgreSQL database dump"
content_check_status=$?
set -o pipefail
if [ "$content_check_status" -ne 0 ]; then
	log_error "Backup içeriği pg_dump çıktısına benzemiyor — backup BAŞARISIZ."
	exit 1
fi

# ── Atomik yayınlama: aynı dosya sisteminde `mv` atomiktir; yarım kalan
#    dosya asla `final_path` adıyla görünmez. ────────────────────────────
mv "$tmp_path" "$final_path"
trap - ERR

sha256sum "$final_path" | awk '{print $1}' >"$checksum_path"

backup_size="$(du -h "$final_path" | cut -f1)"
log_info "Backup tamamlandı: ${final_path} (${backup_size})"
log_info "Checksum: $(cat "$checksum_path")"

# ── Retention: yalnız bu script'in ürettiği dosya deseniyle eşleşenler ───
deleted_count=0
while IFS= read -r old_file; do
	rm -f "$old_file" "${old_file}.sha256"
	log_info "Retention: silindi ${old_file} (> ${RETENTION_DAYS} gün)"
	deleted_count=$((deleted_count + 1))
done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'ivac-postgres-*.sql.gz' -mtime "+${RETENTION_DAYS}" 2>/dev/null)
log_info "Retention: ${deleted_count} eski backup silindi (politika: ${RETENTION_DAYS} gün)"

log_info "Son başarılı LOCAL backup zamanı güncellendi."
# NOT (CODEX_AUDIT_PHASE_6.md YÜKSEK-1): local ve off-site başarı zaman
# damgaları BİLEREK AYRI dosyalarda tutulur. Tek bir `.last-success` off-site
# adımından ÖNCE yazılırsa, off-site yükleme başarısız olduğunda bile
# monitoring "son başarılı backup" olarak bu (yalnız-local) zamanı görür —
# felaket kurtarma hedefinin güncel OLMADIĞI gizlenmiş olur. `.last-remote-success`
# yalnız off-site yükleme GERÇEKTEN başarılı olduğunda yazılır (aşağıda).
# NOT (CODEX_REAUDIT_PHASE_6.md, backup güvenilirliği): status dosyaları da
# `mv` ile ATOMİK yazılır — aynı anda `backup-status`/monitoring bu dosyayı
# okursa asla yarım/kesik bir zaman damgası GÖRMEZ.
date -u +%Y-%m-%dT%H:%M:%SZ >"${BACKUP_DIR}/.tmp.last-local-success"
mv "${BACKUP_DIR}/.tmp.last-local-success" "${BACKUP_DIR}/.last-local-success"

# ── Off-site (opsiyonel — credential yoksa güvenle atlanır, ayrıntı için
#    bkz. offsite-backup.sh) ──────────────────────────────────────────────
if [ "${BACKUP_REMOTE_ENABLED:-false}" = "true" ]; then
	log_info "Off-site backup etkin — offsite-backup.sh çağrılıyor."
	# Off-site upload başarısız olursa bu script de BAŞARISIZ sayılmalı —
	# "yalnız local'e yazıldı ama görev başarılı göründü" durumu YOK.
	if ! "${SCRIPT_DIR}/offsite-backup.sh" "$final_path"; then
		log_error "Off-site backup BAŞARISIZ oldu — local backup var ama felaket kurtarma hedefi güncel DEĞİL."
		exit 1
	fi
	log_info "Son başarılı OFF-SITE backup zamanı güncellendi."
	date -u +%Y-%m-%dT%H:%M:%SZ >"${BACKUP_DIR}/.tmp.last-remote-success"
	mv "${BACKUP_DIR}/.tmp.last-remote-success" "${BACKUP_DIR}/.last-remote-success"
else
	log_info "BACKUP_REMOTE_ENABLED=false — yalnız local backup alındı. Bu felaket kurtarma için YETERLİ DEĞİLDİR (bkz. docs/production/BACKUP_AND_RESTORE.md)."
fi

log_info "postgres-backup.sh tamamlandı (exit 0)."
