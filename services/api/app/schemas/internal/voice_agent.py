from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")


def _validate_event_id(value: str) -> str:
    if not _EVENT_ID_RE.fullmatch(value):
        raise ValueError("invalid event id")
    return value


def _validate_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value


class InternalErrorCode(StrEnum):
    INTERNAL_AUTH_REQUIRED = "INTERNAL_AUTH_REQUIRED"
    INTERNAL_AUTH_INVALID = "INTERNAL_AUTH_INVALID"
    CALL_NOT_FOUND = "CALL_NOT_FOUND"
    CALL_NOT_DIALABLE = "CALL_NOT_DIALABLE"
    CALL_ALREADY_TERMINAL = "CALL_ALREADY_TERMINAL"
    LEAD_NOT_FOUND = "LEAD_NOT_FOUND"
    CAMPAIGN_NOT_FOUND = "CAMPAIGN_NOT_FOUND"
    PROMPT_NOT_CONFIGURED = "PROMPT_NOT_CONFIGURED"
    PRICING_NOT_CONFIGURED = "PRICING_NOT_CONFIGURED"
    SUPPRESSED_PHONE = "SUPPRESSED_PHONE"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    DUPLICATE_EVENT_CONFLICT = "DUPLICATE_EVENT_CONFLICT"
    TRANSCRIPT_STORAGE_DISABLED = "TRANSCRIPT_STORAGE_DISABLED"
    TOOL_CALL_INVALID = "TOOL_CALL_INVALID"
    HUMAN_TRANSFER_DISABLED = "HUMAN_TRANSFER_DISABLED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


class InternalError(StrictModel):
    code: InternalErrorCode
    message: str
    request_id: str


class InternalErrorResponse(StrictModel):
    error: InternalError


class BootstrapLead(StrictModel):
    business_name: str
    sector: str | None
    city: str | None
    district: str | None
    website: str | None
    phone_e164: str
    phone_last_four: str | None


class BootstrapCampaign(StrictModel):
    campaign_id: uuid.UUID | None
    name: str | None
    conversation_engine: str
    model: str
    voice: str
    max_call_duration_seconds: int


class AgentConfiguration(StrictModel):
    prompt_version_id: uuid.UUID
    system_prompt: str
    opening_script: str
    objective: str
    objection_rules: str
    tool_policy: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseItem(StrictModel):
    category: str
    title: str
    content: str


class TelephonyContext(StrictModel):
    outbound_trunk_id: str
    caller_id: str | None
    sip_transport: str
    codec_preferences: list[str]


class PolicyContext(StrictModel):
    recording_enabled: bool
    transcript_storage_enabled: bool
    human_transfer_enabled: bool


class BootstrapResponse(StrictModel):
    call_id: uuid.UUID
    lead: BootstrapLead
    campaign: BootstrapCampaign
    agent_configuration: AgentConfiguration
    knowledge_base: list[KnowledgeBaseItem]
    telephony: TelephonyContext
    policy: PolicyContext


class DialPlanResponse(StrictModel):
    call_id: uuid.UUID
    phone_e164: str
    sip_trunk_id: str
    caller_id: str | None
    room_name: str
    participant_identity: str
    participant_name: str
    max_call_duration_seconds: int


class AgentEventType(StrEnum):
    AGENT_JOB_STARTED = "agent_job_started"
    AGENT_JOB_FAILED = "agent_job_failed"
    SIP_PARTICIPANT_CREATING = "sip_participant_creating"
    DIALING = "dialing"
    RINGING = "ringing"
    ANSWERED = "answered"
    AGENT_SESSION_STARTED = "agent_session_started"
    USER_SPEECH_STARTED = "user_speech_started"
    USER_SPEECH_STOPPED = "user_speech_stopped"
    AGENT_SPEECH_STARTED = "agent_speech_started"
    AGENT_SPEECH_STOPPED = "agent_speech_stopped"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"
    TRANSFER_STARTED = "transfer_started"
    TRANSFER_COMPLETED = "transfer_completed"
    TRANSFER_FAILED = "transfer_failed"
    USAGE_UPDATED = "usage_updated"
    CALL_DISCONNECTED = "call_disconnected"
    AGENT_SESSION_ENDED = "agent_session_ended"


class LifecycleEventIn(StrictModel):
    event_id: str = Field(max_length=120)
    event_type: AgentEventType
    occurred_at: datetime
    sequence: int | None = Field(default=None, ge=0, le=1_000_000)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def _event_id(cls, value: str) -> str:
        return _validate_event_id(value)

    @field_validator("occurred_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return _validate_aware(value)


class GenericAcceptedResponse(StrictModel):
    status: str
    idempotent: bool = False
    detail: str | None = None


class TranscriptTurnIn(StrictModel):
    turn_id: str = Field(max_length=120)
    speaker: Literal["user", "agent", "system"]
    text: str = Field(min_length=1, max_length=4000)
    started_at: datetime
    ended_at: datetime
    is_final: bool = True
    sequence: int = Field(ge=0, le=1_000_000)

    @field_validator("turn_id")
    @classmethod
    def _turn_id(cls, value: str) -> str:
        return _validate_event_id(value)

    @field_validator("started_at", "ended_at")
    @classmethod
    def _aware_dt(cls, value: datetime) -> datetime:
        return _validate_aware(value)

    @model_validator(mode="after")
    def _valid_range(self) -> TranscriptTurnIn:
        if self.ended_at < self.started_at:
            raise ValueError("ended_at cannot be before started_at")
        return self


class UsageSourceIn(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class UsageUpdateIn(StrictModel):
    usage_event_id: str = Field(max_length=120)
    provider: str = Field(min_length=2, max_length=40)
    model: str = Field(min_length=2, max_length=80)
    input_audio_tokens: int = Field(default=0, ge=0, le=10_000_000)
    cached_input_audio_tokens: int = Field(default=0, ge=0, le=10_000_000)
    output_audio_tokens: int = Field(default=0, ge=0, le=10_000_000)
    input_text_tokens: int = Field(default=0, ge=0, le=10_000_000)
    cached_input_text_tokens: int = Field(default=0, ge=0, le=10_000_000)
    output_text_tokens: int = Field(default=0, ge=0, le=10_000_000)
    reasoning_tokens: int | None = Field(default=None, ge=0, le=10_000_000)
    is_final: bool = False
    occurred_at: datetime
    usage_source: UsageSourceIn = UsageSourceIn.PROVIDER_REPORTED

    @field_validator("usage_event_id")
    @classmethod
    def _usage_event_id(cls, value: str) -> str:
        return _validate_event_id(value)

    @field_validator("occurred_at")
    @classmethod
    def _occurred(cls, value: datetime) -> datetime:
        return _validate_aware(value)


class UsageResponse(StrictModel):
    status: str
    idempotent: bool = False
    estimated_ai_cost_usd: str
    usage_source: str


class ToolBase(StrictModel):
    tool_call_id: str = Field(max_length=120)
    occurred_at: datetime

    @field_validator("tool_call_id")
    @classmethod
    def _tool_call_id(cls, value: str) -> str:
        return _validate_event_id(value)

    @field_validator("occurred_at")
    @classmethod
    def _tool_at(cls, value: datetime) -> datetime:
        return _validate_aware(value)


class InfoToolRequest(ToolBase):
    query: str | None = Field(default=None, max_length=120)
    category: str | None = Field(default=None, max_length=60)


class DemoLinkRequest(ToolBase):
    requested_channel: Literal["whatsapp", "sms", "email"] = "whatsapp"


class CallbackRequest(ToolBase):
    callback_at: datetime
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("callback_at")
    @classmethod
    def _callback_at(cls, value: datetime) -> datetime:
        return _validate_aware(value)


class SimpleToolRequest(ToolBase):
    note: str | None = Field(default=None, max_length=1000)


class SuppressionToolRequest(ToolBase):
    reason: str = Field(min_length=2, max_length=255)


class HumanTransferRequest(ToolBase):
    reason: str | None = Field(default=None, max_length=500)


class FinalizeOutcomeRequest(ToolBase):
    outcome: str = Field(max_length=40)
    safe_summary: str | None = Field(default=None, max_length=4000)
    interest_level: Literal["low", "medium", "high"] | None = None
    callback_at: datetime | None = None
    demo_requested: bool = False
    transfer_requested: bool = False
    notes: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("callback_at")
    @classmethod
    def _callback_optional(cls, value: datetime | None) -> datetime | None:
        return _validate_aware(value) if value is not None else None


class ToolResponse(StrictModel):
    status: str
    idempotent: bool = False
    result: dict[str, Any]


class CompletionIn(StrictModel):
    completion_event_id: str = Field(max_length=120)
    disconnect_reason: str = Field(min_length=2, max_length=80)
    ended_at: datetime
    duration_seconds: int = Field(ge=0, le=86_400)
    final_usage_event_id: str | None = Field(default=None, max_length=120)
    # RFC 3261 SIP durum kodundan türetilen sınıflandırma (bkz.
    # services/voice-agent/agent/errors.py::classify_sip_status). Yalnız
    # `disconnect_reason == "sip_failure"` iken anlamlıdır; call status/outcome
    # ayrımı (busy/no_answer/rejected/...) için kullanılır — CODEX_AUDIT_PHASE_4_FIX.md
    # YÜKSEK-3. Backward-compatible: opsiyonel, eski voice-agent sürümleri
    # göndermese de `/complete` eskisi gibi COMPLETED/FAILED'a düşer.
    sip_reason: str | None = Field(default=None, max_length=40)

    @field_validator("completion_event_id")
    @classmethod
    def _completion_id(cls, value: str) -> str:
        return _validate_event_id(value)

    @field_validator("ended_at")
    @classmethod
    def _ended_at(cls, value: datetime) -> datetime:
        return _validate_aware(value)
