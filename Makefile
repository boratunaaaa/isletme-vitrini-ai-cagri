SHELL := /bin/bash
COMPOSE_DEV := docker compose -f docker-compose.dev.yml
COMPOSE_PROD := docker compose -f compose.production.yml --env-file .env.production
API := services/api
AGENT := services/voice-agent

.PHONY: help setup infra-up infra-down db-upgrade db-downgrade db-revision seed bootstrap-admin \
        api worker beat agent web dev lint typecheck test test-py test-e2e build check \
        prod-config prod-build prod-up prod-down prod-logs prod-health prod-migrate \
        prod-bootstrap-admin backup backup-status backup-verify-all restore-smoke-test \
        prod-destroy-volumes

help:
	@grep -E '^[a-zA-Z_-]+:' Makefile | sed 's/:.*//' | sort -u

setup: ## Bağımlılıkları kur (pnpm + uv)
	pnpm install
	cd $(API) && uv sync --all-extras
	cd $(AGENT) && uv sync --all-extras

infra-up: ## Lokal Postgres + Redis başlat
	$(COMPOSE_DEV) up -d postgres redis

infra-down:
	$(COMPOSE_DEV) down

livekit-up: ## Lokal LiveKit + SIP (opsiyonel, kaynak ister)
	$(COMPOSE_DEV) --profile livekit up -d

db-upgrade:
	cd $(API) && uv run alembic upgrade head

db-downgrade:
	cd $(API) && uv run alembic downgrade base

db-revision:
	cd $(API) && uv run alembic revision --autogenerate -m "$(m)"

seed:
	cd $(API) && uv run python -m app.seed

bootstrap-admin:
	cd $(API) && uv run python -m app.bootstrap

api:
	cd $(API) && uv run uvicorn app.main:app --reload --port 8000

worker:
	cd $(API) && uv run celery -A app.worker.celery_app worker -l info -Q default,calls

beat:
	cd $(API) && uv run celery -A app.worker.celery_app beat -l info

agent:
	@test -f $(AGENT)/agent/main.py || (echo "services/voice-agent henüz Aşama 1 kapsamında oluşturulmadı"; exit 1)
	cd $(AGENT) && uv run python -m agent.main dev

web:
	@test -f apps/web/package.json || (echo "apps/web henüz oluşturulmadı"; exit 1)
	pnpm --filter @ivac/web dev

lint:
	cd $(API) && uv run ruff check .

typecheck:
	cd $(API) && uv run mypy app

test-py:
	cd $(API) && uv run pytest -q

test:
	$(MAKE) test-py

test-e2e:
	pnpm --filter @ivac/e2e test

build:
	pnpm build

check: lint typecheck test ## Aşama 1 API kalite kapıları
	$(COMPOSE_DEV) config -q
	@echo "API AŞAMA 1 KONTROLLERİ GEÇTİ"

# ─── Production (compose.production.yml) ────────────────────────────────
# Önce .env.production.example'dan .env.production oluşturun (gerçek
# secret'larla doldurup asla commit etmeyin — bkz. docs/production/DEPLOYMENT.md).

prod-config: ## Production compose interpolation/şema doğrulaması (secret basmaz)
	$(COMPOSE_PROD) config -q
	@echo "compose.production.yml GEÇERLİ"

prod-build: ## Tüm production image'larını derle
	$(COMPOSE_PROD) build

prod-up: ## Production stack'i başlat (migrate ayrı adımdır, otomatik çalışmaz)
	$(COMPOSE_PROD) up -d

prod-down: ## Production stack'i durdur (volume'lara DOKUNMAZ)
	$(COMPOSE_PROD) down

prod-destroy-volumes: ## TEHLİKELİ: tüm production volume'larını (DB dahil) SİLER — force gerektirir
	@if [ "$(force)" != "yes" ]; then \
		echo "REDDEDİLDİ: bu komut PostgreSQL/Redis/Caddy volume'larını KALICI olarak siler."; \
		echo "Gerçekten istiyorsanız: make prod-destroy-volumes force=yes"; \
		exit 1; \
	fi
	$(COMPOSE_PROD) down -v

prod-logs: ## Tüm servislerin loglarını takip et (service=<ad> ile filtrelenebilir)
	$(COMPOSE_PROD) logs -f --tail=200 $(service)

prod-health: ## Tüm servislerin sağlık durumunu göster
	$(COMPOSE_PROD) ps

prod-migrate: ## Tek seferlik, kontrollü migration (birden fazla replika eşzamanlı ÇALIŞTIRMAZ)
	$(COMPOSE_PROD) run --rm migrate

prod-bootstrap-admin: ## İlk yönetici kullanıcıyı oluştur (yalnız ilk kurulumda bir kez)
	$(COMPOSE_PROD) run --rm api python -m app.bootstrap

# ─── Backup / Restore ────────────────────────────────────────────────────

backup: ## Manuel PostgreSQL backup tetikle (yerel + yapılandırılmışsa off-site)
	$(COMPOSE_PROD) run --rm backup /scripts/postgres-backup.sh

backup-status: ## Son başarılı backup zamanlarını (local + off-site AYRI) ve mevcut dosyaları göster
	$(COMPOSE_PROD) run --rm --entrypoint sh backup -c \
		'echo "Son başarılı LOCAL backup:"; cat /backups/.last-local-success 2>/dev/null || echo "(henüz backup alınmadı)"; echo; echo "Son başarılı OFF-SITE backup:"; cat /backups/.last-remote-success 2>/dev/null || echo "(off-site hiç başarılı olmadı veya BACKUP_REMOTE_ENABLED=false)"; echo; echo "Mevcut backup dosyaları:"; ls -lh /backups/*.sql.gz 2>/dev/null || echo "(yok)"'

backup-verify-all: ## Tüm mevcut backup dosyalarının checksum/bütünlüğünü doğrula
	$(COMPOSE_PROD) run --rm backup /scripts/verify-backup.sh --all

restore-smoke-test: ## Disposable veritabanında uçtan uca restore tatbikatı (production'a DOKUNMAZ)
	$(COMPOSE_PROD) run --rm backup /scripts/restore-smoke-test.sh
