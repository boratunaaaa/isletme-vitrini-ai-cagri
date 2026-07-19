#!/usr/bin/env bash
# Ortak yardımcılar: `scripts/backup/*.sh` tarafından `source` edilir.
# Bağımsız çalıştırılabilir bir script DEĞİLDİR.

log_info() {
	printf '[%s] INFO  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

log_error() {
	printf '[%s] ERROR %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

# Zorunlu ortam değişkenlerini kontrol eder; eksikse AÇIK hatayla (sessiz
# varsayılana düşmeden) çıkar. Değerleri ASLA loglamaz (yalnız isim).
require_env() {
	local missing=()
	local name
	for name in "$@"; do
		if [ -z "${!name:-}" ]; then
			missing+=("$name")
		fi
	done
	if [ ${#missing[@]} -gt 0 ]; then
		log_error "Zorunlu ortam değişkeni eksik: ${missing[*]}"
		exit 1
	fi
}

# PGPASSWORD dahil hiçbir secret'ı komut satırı argümanına veya `ps` çıktısına
# taşımadan libpq'nun ortam değişkeni sözleşmesine güveniyoruz (PGHOST/
# PGPORT/PGUSER/PGPASSWORD/PGDATABASE zaten pg_dump/psql/pg_restore
# tarafından otomatik okunur — bu yüzden script'lerde `-h`/`-U`/`--password`
# gibi bayraklar KULLANILMAZ).
