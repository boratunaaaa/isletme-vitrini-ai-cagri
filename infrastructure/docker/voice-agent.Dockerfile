FROM python:3.11-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.9.17

COPY services/voice-agent/pyproject.toml services/voice-agent/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/voice-agent/agent ./agent
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    VOICE_AGENT_ENV=production

WORKDIR /app

RUN addgroup --system voiceagent && adduser --system --ingroup voiceagent voiceagent

COPY --from=builder /app /app

USER voiceagent

EXPOSE 8081

# NOT (CODEX_REAUDIT_PHASE_6.md, "voice-agent healthcheck gerçekliği"):
# `--check-config` yalnız env değişkenlerinin DOLU olduğunu doğrular, gerçek
# worker sürecinin başladığını veya LiveKit'e bağlanabildiğini KANITLAMAZ —
# yanlış/eksik credential'larla bile config validasyonu geçebilirdi. LiveKit
# Agents SDK'sının kendi `AgentServer.run()`'ı zaten gerçek bir `GET /`
# health endpoint'i sunuyor (`livekit/agents/worker.py::health_check`,
# port 8081 — `WorkerOptions.port`'un `start` alt komutunda kullanılan
# production varsayılanı): inference executor çökmüşse veya LiveKit'e
# bağlanma denemesi TÜM retry'leri (`max_retry=16`) tükettiyse 503, aksi
# halde (bağlı VEYA hâlâ retry deniyor) 200 döner. Bu, container'ın yalnız
# config geçerli olduğu için değil, gerçek worker HTTP sunucusu ayakta VE
# SDK'nın kendi bağlantı durumu izlemesi başarısız DEĞİLKEN healthy
# sayılmasını sağlar — ampirik olarak doğrulandı (bkz. PRODUCTION_INFRA_REPORT.md).
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8081/', timeout=3).status == 200 else 1)"

# NOT (PRODUCTION_INFRA_REPORT.md): `start` gerçek LiveKit Agents CLI (Typer
# tabanlı `agents.cli.run_app`) alt komutudur — `agent/main.py` okunarak ve
# `uv run python -m agent.main start` ile GERÇEKTEN çalıştırılarak
# doğrulandı (worker bootstrap loglarını üretiyor). Argümansız `python -m
# agent.main` çalıştırmak Typer'ın hangi modu (dev/start/console/connect)
# seçeceği belirsiz bırakıyordu; `start` production worker modudur ve
# LIVEKIT_URL/LIVEKIT_API_KEY/LIVEKIT_API_SECRET'i ortam değişkeninden okur.
CMD ["python", "-m", "agent.main", "start"]
