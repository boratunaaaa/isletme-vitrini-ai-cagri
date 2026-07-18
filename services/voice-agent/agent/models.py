from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BootstrapLead(StrictModel):
    business_name: str
    sector: str | None = None
    city: str | None = None
    district: str | None = None
    website: str | None = None
    phone_e164: str
    phone_last_four: str | None = None


class BootstrapCampaign(StrictModel):
    campaign_id: uuid.UUID | None = None
    name: str | None = None
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
    caller_id: str | None = None
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
    caller_id: str | None = None
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


class GenericAcceptedResponse(StrictModel):
    status: str
    idempotent: bool = False
    detail: str | None = None


class LifecycleEventIn(StrictModel):
    event_id: str
    event_type: AgentEventType
    occurred_at: datetime
    sequence: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class TranscriptTurnIn(StrictModel):
    turn_id: str
    speaker: Literal["user", "agent", "system"]
    text: str = Field(min_length=1, max_length=4000)
    started_at: datetime
    ended_at: datetime
    is_final: bool = True
    sequence: int

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
    usage_event_id: str
    provider: str = "openai"
    model: str
    input_audio_tokens: int = 0
    cached_input_audio_tokens: int = 0
    output_audio_tokens: int = 0
    input_text_tokens: int = 0
    cached_input_text_tokens: int = 0
    output_text_tokens: int = 0
    reasoning_tokens: int | None = None
    is_final: bool = False
    occurred_at: datetime
    usage_source: UsageSourceIn = UsageSourceIn.PROVIDER_REPORTED


class UsageResponse(StrictModel):
    status: str
    idempotent: bool = False
    estimated_ai_cost_usd: str
    usage_source: str


class CompletionIn(StrictModel):
    completion_event_id: str
    disconnect_reason: str
    ended_at: datetime
    duration_seconds: int
    final_usage_event_id: str | None = None
    # RFC 3261 tabanlı SIP sınıflandırması (bkz. agent/errors.py::classify_sip_status).
    # Yalnız disconnect_reason == "sip_failure" iken anlamlı; backend bunu
    # call status/outcome ayrımı (busy/no_answer/rejected/...) için kullanır
    # (CODEX_AUDIT_PHASE_4_FIX.md YÜKSEK-3).
    sip_reason: str | None = None


class ToolResponse(StrictModel):
    status: str
    idempotent: bool = False
    result: dict[str, Any]


class InternalErrorPayload(StrictModel):
    code: str
    message: str
    request_id: str


class InternalErrorResponse(StrictModel):
    error: InternalErrorPayload


class ToolDefinition(StrictModel):
    name: str
    backend_path: str
    description: str
    parameters: dict[str, Any]


class JobMetadata(StrictModel):
    call_id: uuid.UUID


class DisconnectReason(StrEnum):
    REMOTE_HANGUP = "remote_hangup"
    AGENT_HANGUP = "agent_hangup"
    TIMEOUT = "timeout"
    SIP_FAILURE = "sip_failure"
    OPENAI_FAILURE = "openai_failure"
    AGENT_ERROR = "agent_error"
    COMPLETED = "completed"


ALLOWED_MODELS = {"gpt-realtime-2.1-mini", "gpt-realtime-2.1"}
ALLOWED_VOICES = {
    "marin",
    "cedar",
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "sage",
    "shimmer",
    "verse",
}
