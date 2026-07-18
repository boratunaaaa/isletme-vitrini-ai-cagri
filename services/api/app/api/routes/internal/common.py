from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.deps import InternalServiceContext
from app.models.call import Call
from app.models.enums import TERMINAL_CALL_STATUSES
from app.schemas.internal.voice_agent import InternalErrorCode


class InternalAPIError(Exception):
    def __init__(
        self,
        code: InternalErrorCode,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def error_response(error: InternalAPIError, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code.value,
                "message": error.message,
                "request_id": request_id,
            }
        },
    )


def request_id_from(request: Request, ctx: InternalServiceContext | None = None) -> str:
    return ctx.request_id if ctx else request.headers.get("X-Request-ID", "")


def get_call_or_error(db: Session, call_id: uuid.UUID) -> Call:
    call = db.get(Call, call_id)
    if call is None:
        raise InternalAPIError(
            InternalErrorCode.CALL_NOT_FOUND,
            "Call not found.",
            status.HTTP_404_NOT_FOUND,
        )
    return call


def ensure_not_terminal(call: Call) -> None:
    if call.status in [status_.value for status_ in TERMINAL_CALL_STATUSES]:
        raise InternalAPIError(
            InternalErrorCode.CALL_ALREADY_TERMINAL,
            "Call is already terminal.",
            status.HTTP_409_CONFLICT,
        )


def raise_http(error: InternalAPIError) -> None:
    raise HTTPException(
        status_code=error.status_code,
        detail={"code": error.code.value, "message": error.message},
    )


def as_result(status_text: str, **values: Any) -> dict[str, Any]:
    return {"status": status_text, **values}
