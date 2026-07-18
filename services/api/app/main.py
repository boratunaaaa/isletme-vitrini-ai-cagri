from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.api.routes import auth, calls, campaigns, content, lead_import, leads, live, ops, users
from app.api.routes.internal import router as internal_router
from app.config import get_settings
from app.core.logging import configure_logging, request_id_var
from app.core.redis import get_redis
from app.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    logger.info("API starting: %s", settings.APP_NAME)
    yield
    logger.info("API stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="İşletme Vitrini AI Çağrı Merkezi API",
        version="0.1.0",
        lifespan=lifespan,
    )

    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "request method=%s path=%s elapsed_ms=%s failed=true",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            request_id_var.reset(token)
            raise
        else:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "request method=%s path=%s elapsed_ms=%s",
                request.method,
                request.url.path,
                elapsed_ms,
            )
            request_id_var.reset(token)
            response.headers["X-Request-ID"] = request_id
            return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("validation_error path=%s errors=%s", request.url.path, len(exc.errors()))
        if request.url.path.startswith("/api/internal/"):
            request_id = request_id_var.get() or request.headers.get("X-Request-ID", "")
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request validation failed.",
                        "request_id": request_id,
                    }
                },
            )
        return JSONResponse(
            status_code=422,
            content={"detail": "İstek doğrulanamadı", "errors": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if request.url.path.startswith("/api/internal/"):
            request_id = request_id_var.get() or request.headers.get("X-Request-ID", "")
            detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": {
                        "code": detail.get("code", "VALIDATION_ERROR"),
                        "message": detail.get("message", "Internal request failed."),
                        "request_id": request_id,
                    }
                },
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error path=%s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Beklenmeyen bir hata oluştu"},
        )

    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    def ready() -> JSONResponse:
        checks = {"database": _check_database(), "redis": _check_redis()}
        is_ready = all(value == "ok" for value in checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ready" if is_ready else "not_ready", "checks": checks},
        )

    api_prefix = "/api"
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(leads.router, prefix=api_prefix)
    app.include_router(lead_import.router, prefix=api_prefix)
    app.include_router(campaigns.router, prefix=api_prefix)
    app.include_router(calls.router, prefix=api_prefix)
    app.include_router(ops.router, prefix=api_prefix)
    app.include_router(content.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(live.router, prefix=api_prefix)
    app.include_router(internal_router, prefix=api_prefix)
    return app


def _check_database() -> str:
    try:
        with get_sessionmaker()() as db:
            db.execute(text("select 1"))
        return "ok"
    except Exception:
        logger.warning("readiness database check failed")
        return "error"


def _check_redis() -> str:
    try:
        if get_redis().ping():
            return "ok"
    except Exception:
        logger.warning("readiness redis check failed")
    return "error"


app = create_app()
