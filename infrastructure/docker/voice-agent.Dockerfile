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

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -m agent.main --check-config || exit 1

CMD ["python", "-m", "agent.main"]
