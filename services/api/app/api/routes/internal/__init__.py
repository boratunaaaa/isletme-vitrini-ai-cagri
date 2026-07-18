from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.internal import calls, health, tools

router = APIRouter(prefix="/internal/v1", tags=["internal"])
router.include_router(health.router)
router.include_router(calls.router)
router.include_router(tools.router)
