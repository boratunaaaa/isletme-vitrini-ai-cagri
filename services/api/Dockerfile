# Production image: FastAPI backend + Celery worker/beat + Alembic migration.
# Aynı image `compose.production.yml`'de `api`/`worker`/`beat`/`migrate`
# servislerinin hepsinde farklı `command:` ile kullanılır (kod tabanı aynı,
# yeniden derlemeye gerek yok).
#
# Build context: repo KÖKÜ olmalı (`docker build -f services/api/Dockerfile .`)
# — bu, tek bir `.dockerignore`'un tüm servisler için geçerli olmasını sağlar.

FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.17

# Bağımlılıkları önce kur (kaynak kod değişse bile bu katman cache'te kalır).
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Gerçek kaynak: yalnız çalışma zamanında ihtiyaç duyulanlar (test dosyaları
# ve dokümanlar `.dockerignore` ile zaten dışlanıyor).
COPY services/api/app ./app
COPY services/api/alembic ./alembic
COPY services/api/alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production

WORKDIR /app

RUN addgroup --system ivac && adduser --system --ingroup ivac ivac

COPY --from=builder /app /app

USER ivac

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

# Varsayılan: API sunucusu. `worker`/`beat`/`migrate` servisleri
# `compose.production.yml`'de bu CMD'yi override eder — hiçbiri image içinde
# `--reload` veya kaynak bind-mount KULLANMAZ (production'da hot-reload yok).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
