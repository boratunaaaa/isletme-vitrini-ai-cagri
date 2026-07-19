#!/usr/bin/env bash
# Off-site şifreli backup: `restic` ile S3-uyumlu (veya restic'in desteklediği
# başka) bir uzak repository'ye yükler. Local backup TEK BAŞINA gerçek bir
# felaket kurtarma çözümü DEĞİLDİR — bu script olmadan (veya
# BACKUP_REMOTE_ENABLED=false iken) sistem yalnız "local-only backup" olarak
# raporlanmalıdır (bkz. docs/production/BACKUP_AND_RESTORE.md).
#
# Kullanım: offsite-backup.sh <local-backup-dosyası>
#
# Gerekli ortam değişkenleri (yalnız isim — gerçek değer asla bu dosyaya
# veya herhangi bir dokümana yazılmaz):
#   RESTIC_REPOSITORY, RESTIC_PASSWORD
#   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
#     (RESTIC_REPOSITORY bir s3:// hedefiyse)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "${SCRIPT_DIR}/lib.sh"

backup_file="${1:?Kullanım: offsite-backup.sh <local-backup-dosyası>}"
if [ ! -f "$backup_file" ]; then
	log_error "Dosya bulunamadı: ${backup_file}"
	exit 1
fi

require_env RESTIC_REPOSITORY RESTIC_PASSWORD

RETENTION_DAILY="${RESTIC_RETENTION_DAILY:-14}"
RETENTION_WEEKLY="${RESTIC_RETENTION_WEEKLY:-8}"
RETENTION_MONTHLY="${RESTIC_RETENTION_MONTHLY:-6}"
# NOT (bu turda ampirik olarak keşfedildi — CODEX_REAUDIT_PHASE_6.md kapsamına
# dahil "backup güvenilirliği"): hiçbir `restic` çağrısında zaman aşımı YOKTU.
# Yanlış yapılandırılmış/erişilemeyen bir off-site hedef (yanlış DNS adı,
# ağ kesintisi) `restic`in kendi HTTP client'ını SÜRESİZ bekletebiliyordu —
# gerçek bir çalışmada bu, cron/systemd tetiklemesini bloke edip
# "başarısız" durumun asla raporlanmamasına yol açardı. Her `restic` çağrısı
# artık `timeout` ile sınırlanır; aşılırsa normal bir başarısızlık gibi
# ele alınır (exit code != 0), sessizce asılı KALMAZ.
RESTIC_TIMEOUT_SECONDS="${RESTIC_TIMEOUT_SECONDS:-300}"
# NOT (CODEX_FINAL_AUDIT_PHASE_6.md ORTA-1): baştaki/sondaki whitespace
# kırpılır ("yalnız whitespace" veya boş sonuç -> güvenli varsayılana
# düşer, tıpkı ortam değişkeni hiç TANIMLANMAMIŞ gibi ele alınır).
RESTIC_TIMEOUT_SECONDS="$(printf '%s' "$RESTIC_TIMEOUT_SECONDS" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
if [ -z "$RESTIC_TIMEOUT_SECONDS" ]; then
	RESTIC_TIMEOUT_SECONDS=300
fi
# NOT (CODEX_FINAL_AUDIT_PHASE_6.md ORTA-1): `timeout 0 <cmd>` GNU coreutils
# semantiğinde "zaman aşımını DEVRE DIŞI bırak" anlamına gelir (0 saniye
# DEĞİL) — bir operatör bu değeri yanlışlıkla `0` yaparsa hang koruması
# SESSİZCE etkisiz kalırdı (ampirik olarak doğrulandı: `timeout 0 sleep 5`
# başarıyla `sleep`in normal bitmesini bekler, KESMEZ). Negatif/ondalık/
# sayısal-olmayan değerler de aynı şekilde `timeout`'a öngörülemez şekilde
# geçilebilir. Bu yüzden restic hiç ÇAĞRILMADAN ÖNCE fail-fast doğrulanır —
# hatalı değerle restic BAŞLATILMAZ, hiçbir ağ çağrısı yapılmaz.
_RESTIC_TIMEOUT_MAX_SECONDS=3600
if ! printf '%s' "$RESTIC_TIMEOUT_SECONDS" | grep -qE '^[0-9]+$'; then
	log_error "RESTIC_TIMEOUT_SECONDS geçersiz: yalnız pozitif tam sayı (saniye) olabilir — ondalık, negatif veya sayısal olmayan değer KABUL EDİLMEZ."
	exit 1
fi
if [ "$RESTIC_TIMEOUT_SECONDS" -le 0 ]; then
	log_error "RESTIC_TIMEOUT_SECONDS=0 (veya daha küçük) KABUL EDİLMEZ — coreutils 'timeout 0' zaman aşımını DEVRE DIŞI bırakır, bu backup hang korumasını sessizce kapatır."
	exit 1
fi
if [ "$RESTIC_TIMEOUT_SECONDS" -gt "$_RESTIC_TIMEOUT_MAX_SECONDS" ]; then
	log_error "RESTIC_TIMEOUT_SECONDS geçersiz: üst sınır ${_RESTIC_TIMEOUT_MAX_SECONDS} saniyeyi (1 saat) AŞAMAZ — daha uzun bir off-site aktarım gerekiyorsa bu üst sınırı bilinçli olarak scripti düzenleyerek artırın."
	exit 1
fi
# `timeout` ayrı bir süreç olarak kendi PATH aramasını yapıp `restic`
# binary'sini doğrudan exec eder — bu, bash fonksiyon tablosunu (yalnız bu
# shell sürecinin belleğinde var olur) hiç görmez, bu yüzden isim çakışması
# (fonksiyon adı = binary adı) burada sorun DEĞİLDİR; `command` builtin'i
# GEREKMEZ (`timeout` onu bir binary sanıp exec etmeye çalışır, başarısız olur).
restic() { timeout "$RESTIC_TIMEOUT_SECONDS" restic "$@"; }

# restic repository ilk kullanımda mevcut değilse başlat (idempotent —
# zaten başlatılmışsa `restic init` hata verir, bu BEKLENEN ve zararsızdır).
if ! restic snapshots --latest 1 >/dev/null 2>&1; then
	log_info "Restic repository henüz başlatılmamış görünüyor, init deneniyor."
	restic init || true
fi

log_info "Restic'e yükleniyor: $(basename "$backup_file")"
if ! restic backup "$backup_file" \
	--tag "ivac-postgres" \
	--host "ivac-production" \
	--quiet; then
	log_error "restic backup BAŞARISIZ oldu (${RESTIC_TIMEOUT_SECONDS}s zaman aşımı dahil)."
	exit 1
fi

log_info "Uzak repository bütünlük kontrolü çalıştırılıyor (restic check)."
if ! restic check --quiet; then
	log_error "restic check BAŞARISIZ oldu — uzak repository bütünlüğünden ŞÜPHELENİLMELİ."
	exit 1
fi

log_info "Retention/prune uygulanıyor (günlük=${RETENTION_DAILY} haftalık=${RETENTION_WEEKLY} aylık=${RETENTION_MONTHLY})."
if ! restic forget \
	--tag "ivac-postgres" \
	--host "ivac-production" \
	--keep-daily "$RETENTION_DAILY" \
	--keep-weekly "$RETENTION_WEEKLY" \
	--keep-monthly "$RETENTION_MONTHLY" \
	--prune \
	--quiet; then
	log_error "restic forget/prune başarısız oldu (backup'ın kendisi başarılıydı — yalnız eski snapshot temizliği başarısız)."
	exit 1
fi

log_info "Off-site backup tamamlandı ve doğrulandı."
