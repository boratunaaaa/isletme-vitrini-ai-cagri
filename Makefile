SHELL := /bin/bash
COMPOSE_DEV := docker compose -f docker-compose.dev.yml
API := services/api
AGENT := services/voice-agent

.PHONY: help setup infra-up infra-down db-upgrade db-downgrade db-revision seed bootstrap-admin \
        api worker beat agent web dev lint typecheck test test-py test-e2e build check

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
