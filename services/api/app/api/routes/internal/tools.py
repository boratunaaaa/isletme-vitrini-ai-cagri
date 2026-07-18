from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.internal.common import (
    InternalAPIError,
    ensure_not_terminal,
    error_response,
    get_call_or_error,
)
from app.config import get_settings
from app.deps import InternalServiceContext, get_db, require_internal_service
from app.models.call import CallEvent
from app.models.content import KnowledgeBaseEntry
from app.models.enums import CallbackStatus, CallOutcome, DemoRequestStatus
from app.models.lead import Lead
from app.models.ops import Callback, DemoRequest
from app.schemas.internal.voice_agent import (
    CallbackRequest,
    DemoLinkRequest,
    FinalizeOutcomeRequest,
    HumanTransferRequest,
    InfoToolRequest,
    InternalErrorCode,
    SimpleToolRequest,
    SuppressionToolRequest,
    ToolResponse,
)
from app.services.call_service import finalize_outcome
from app.services.internal_contract import IdempotencyConflict, idempotent, redact_text
from app.services.suppression_service import add_suppression

router = APIRouter(prefix="/calls/{call_id}/tools")


def _safe_error(exc: InternalAPIError, ctx: InternalServiceContext) -> JSONResponse:
    return error_response(exc, ctx.request_id)


def _lead(db: Session, call: Any) -> Lead:
    lead = db.get(Lead, call.lead_id)
    if lead is None:
        raise InternalAPIError(InternalErrorCode.LEAD_NOT_FOUND, "Lead not found.", 404)
    return lead


def _event(db: Session, call_id: uuid.UUID, event_type: str, payload: dict[str, Any]) -> None:
    db.add(
        CallEvent(
            call_id=call_id,
            event_type=event_type,
            safe_payload=payload,
            event_timestamp=datetime.now(UTC),
        )
    )


def _tool(
    db: Session,
    *,
    call_id: uuid.UUID,
    external_id: str,
    event_type: str,
    payload: dict[str, Any],
    ctx: InternalServiceContext,
    handler: Any,
) -> ToolResponse | JSONResponse:
    try:
        result, replay = idempotent(
            db,
            call_id=call_id,
            external_id=external_id,
            event_type=event_type,
            payload=payload,
            handler=handler,
        )
        return ToolResponse(status="ok", idempotent=replay, result=result)
    except IdempotencyConflict:
        return _safe_error(
            InternalAPIError(
                InternalErrorCode.DUPLICATE_EVENT_CONFLICT,
                "Duplicate tool call id with different payload.",
                409,
            ),
            ctx,
        )
    except InternalAPIError as exc:
        return _safe_error(exc, ctx)


@router.post("/get-service-information", response_model=ToolResponse, include_in_schema=False)
def get_service_information(
    call_id: uuid.UUID,
    payload: InfoToolRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        get_call_or_error(db, call_id)
        query = select(KnowledgeBaseEntry).where(KnowledgeBaseEntry.is_active.is_(True))
        if payload.category:
            query = query.where(KnowledgeBaseEntry.category == payload.category)
        else:
            query = query.where(KnowledgeBaseEntry.category != "paketler")
        entries = db.scalars(query.order_by(KnowledgeBaseEntry.title).limit(5)).all()
        return {
            "items": [
                {"category": e.category, "title": e.title, "content": e.content} for e in entries
            ]
        }

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:get_service_information",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


@router.post("/get-package-information", response_model=ToolResponse, include_in_schema=False)
def get_package_information(
    call_id: uuid.UUID,
    payload: InfoToolRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        get_call_or_error(db, call_id)
        entries = db.scalars(
            select(KnowledgeBaseEntry)
            .where(
                KnowledgeBaseEntry.is_active.is_(True), KnowledgeBaseEntry.category == "paketler"
            )
            .order_by(KnowledgeBaseEntry.title)
            .limit(10)
        ).all()
        return {
            "currency": "TRY",
            "vat_note": "Seed bilgi bankasındaki açıklamaya bakın.",
            "items": [{"title": e.title, "content": e.content} for e in entries],
        }

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:get_package_information",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


@router.post("/request-demo-link", response_model=ToolResponse, include_in_schema=False)
def request_demo_link(
    call_id: uuid.UUID,
    payload: DemoLinkRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        call = get_call_or_error(db, call_id)
        ensure_not_terminal(call)
        lead = _lead(db, call)
        existing = db.scalars(
            select(DemoRequest).where(
                DemoRequest.call_id == call_id,
                DemoRequest.status == DemoRequestStatus.PENDING.value,
            )
        ).first()
        demo = existing or DemoRequest(
            lead_id=lead.id,
            call_id=call_id,
            requested_channel=payload.requested_channel,
        )
        db.add(demo)
        finalize_outcome(db, call, outcome=CallOutcome.DEMO_REQUESTED, demo_requested=True)
        _event(db, call_id, "tool:request_demo_link", {"channel": payload.requested_channel})
        return {"demo_request_id": str(demo.id), "demo_link_available": bool(lead.demo_link)}

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:request_demo_link",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


@router.post("/schedule-callback", response_model=ToolResponse, include_in_schema=False)
def schedule_callback(
    call_id: uuid.UUID,
    payload: CallbackRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        call = get_call_or_error(db, call_id)
        ensure_not_terminal(call)
        lead = _lead(db, call)
        callback_at = payload.callback_at.astimezone(ZoneInfo(get_settings().APP_TIMEZONE))
        now = datetime.now(ZoneInfo(get_settings().APP_TIMEZONE))
        if callback_at <= now or callback_at > now + timedelta(days=30):
            raise InternalAPIError(
                InternalErrorCode.TOOL_CALL_INVALID, "Invalid callback time.", 422
            )
        existing = db.scalars(
            select(Callback).where(
                Callback.call_id == call_id,
                Callback.status.in_([CallbackStatus.PENDING.value, CallbackStatus.SCHEDULED.value]),
            )
        ).first()
        callback = existing or Callback(
            lead_id=lead.id,
            call_id=call_id,
            callback_at=payload.callback_at,
            notes=redact_text(payload.notes or "") or None,
        )
        db.add(callback)
        finalize_outcome(
            db, call, outcome=CallOutcome.CALLBACK_REQUESTED, callback_at=payload.callback_at
        )
        _event(
            db, call_id, "tool:schedule_callback", {"callback_at": payload.callback_at.isoformat()}
        )
        return {"callback_id": str(callback.id), "callback_at": payload.callback_at.isoformat()}

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:schedule_callback",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


def _mark_outcome_endpoint(outcome: CallOutcome, event_type: str) -> Any:
    def endpoint(
        call_id: uuid.UUID,
        payload: SimpleToolRequest,
        db: Session = Depends(get_db),
        ctx: InternalServiceContext = Depends(require_internal_service),
    ) -> ToolResponse | JSONResponse:
        def handle() -> dict[str, Any]:
            call = get_call_or_error(db, call_id)
            ensure_not_terminal(call)
            finalize_outcome(
                db, call, outcome=outcome, summary=redact_text(payload.note or "") or None
            )
            _event(db, call_id, event_type, {"outcome": outcome.value})
            return {"outcome": outcome.value}

        return _tool(
            db,
            call_id=call_id,
            external_id=payload.tool_call_id,
            event_type=event_type,
            payload=payload.model_dump(mode="json"),
            ctx=ctx,
            handler=handle,
        )

    return endpoint


router.post("/mark-interested", response_model=ToolResponse, include_in_schema=False)(
    _mark_outcome_endpoint(CallOutcome.INTERESTED, "tool:mark_interested")
)
router.post("/mark-not-interested", response_model=ToolResponse, include_in_schema=False)(
    _mark_outcome_endpoint(CallOutcome.NOT_INTERESTED, "tool:mark_not_interested")
)
router.post("/mark-wrong-number", response_model=ToolResponse, include_in_schema=False)(
    _mark_outcome_endpoint(CallOutcome.WRONG_NUMBER, "tool:mark_wrong_number")
)
router.post(
    "/mark-decision-maker-unavailable", response_model=ToolResponse, include_in_schema=False
)(
    _mark_outcome_endpoint(
        CallOutcome.DECISION_MAKER_UNAVAILABLE,
        "tool:mark_decision_maker_unavailable",
    )
)


@router.post("/add-to-suppression-list", response_model=ToolResponse, include_in_schema=False)
def add_to_suppression_list(
    call_id: uuid.UUID,
    payload: SuppressionToolRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        call = get_call_or_error(db, call_id)
        ensure_not_terminal(call)
        lead = _lead(db, call)
        if not lead.phone_hash or not lead.phone_last_four:
            raise InternalAPIError(
                InternalErrorCode.TOOL_CALL_INVALID, "Lead has no callable phone.", 422
            )
        entry = add_suppression(
            db,
            phone_hash=lead.phone_hash,
            phone_last_four=lead.phone_last_four,
            reason=payload.reason,
            source="agent_call",
            lead_id=lead.id,
        )
        finalize_outcome(db, call, outcome=CallOutcome.DO_NOT_CALL)
        _event(db, call_id, "tool:add_to_suppression_list", {"reason": payload.reason})
        return {"suppression_id": str(entry.id), "outcome": CallOutcome.DO_NOT_CALL.value}

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:add_to_suppression_list",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


@router.post("/request-human-transfer", response_model=ToolResponse, include_in_schema=False)
def request_human_transfer(
    call_id: uuid.UUID,
    payload: HumanTransferRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        call = get_call_or_error(db, call_id)
        ensure_not_terminal(call)
        if not get_settings().HUMAN_TRANSFER_ENABLED:
            return {
                "transfer_available": False,
                "code": InternalErrorCode.HUMAN_TRANSFER_DISABLED.value,
            }
        call.transfer_requested = True
        finalize_outcome(
            db, call, outcome=CallOutcome.TRANSFERRED_TO_HUMAN, transfer_requested=True
        )
        _event(db, call_id, "tool:request_human_transfer", {"enabled": True})
        return {"transfer_available": True}

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:request_human_transfer",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


@router.post("/finalize-call-outcome", response_model=ToolResponse, include_in_schema=False)
def finalize_call_outcome(
    call_id: uuid.UUID,
    payload: FinalizeOutcomeRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        call = get_call_or_error(db, call_id)
        ensure_not_terminal(call)
        try:
            outcome = CallOutcome(payload.outcome)
        except ValueError as exc:
            raise InternalAPIError(
                InternalErrorCode.TOOL_CALL_INVALID, "Invalid outcome.", 422
            ) from exc
        if call.outcome and call.outcome != outcome.value:
            raise InternalAPIError(
                InternalErrorCode.TOOL_CALL_INVALID, "Call outcome already finalized.", 409
            )
        if payload.callback_at and outcome != CallOutcome.CALLBACK_REQUESTED:
            raise InternalAPIError(
                InternalErrorCode.TOOL_CALL_INVALID, "Callback time requires callback outcome.", 422
            )
        if payload.demo_requested and outcome != CallOutcome.DEMO_REQUESTED:
            raise InternalAPIError(
                InternalErrorCode.TOOL_CALL_INVALID, "Demo flag requires demo outcome.", 422
            )
        finalize_outcome(
            db,
            call,
            outcome=outcome,
            summary=redact_text(payload.safe_summary or "") or None,
            callback_at=payload.callback_at,
            demo_requested=payload.demo_requested,
            transfer_requested=payload.transfer_requested,
        )
        _event(db, call_id, "tool:finalize_call_outcome", {"outcome": outcome.value})
        return {"outcome": outcome.value}

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:finalize_call_outcome",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )


@router.post("/end-call-safely", response_model=ToolResponse, include_in_schema=False)
def end_call_safely(
    call_id: uuid.UUID,
    payload: SimpleToolRequest,
    db: Session = Depends(get_db),
    ctx: InternalServiceContext = Depends(require_internal_service),
) -> ToolResponse | JSONResponse:
    def handle() -> dict[str, Any]:
        call = get_call_or_error(db, call_id)
        ensure_not_terminal(call)
        _event(db, call_id, "tool:end_call_safely", {"intent": True})
        return {"should_hangup": True, "hangup_performed": False}

    return _tool(
        db,
        call_id=call_id,
        external_id=payload.tool_call_id,
        event_type="tool:end_call_safely",
        payload=payload.model_dump(mode="json"),
        ctx=ctx,
        handler=handle,
    )
