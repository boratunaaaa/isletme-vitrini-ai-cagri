"""Domain enum'ları. DB'de native enum yerine VARCHAR+CHECK olarak saklanır
(migration kolaylığı için)."""

from __future__ import annotations

from enum import StrEnum


class LeadSource(StrEnum):
    GOOGLE_PLACES = "google_places"
    XLSX_IMPORT = "xlsx_import"
    CSV_IMPORT = "csv_import"
    JSON_IMPORT = "json_import"
    MANUAL = "manual"


class LeadStatus(StrEnum):
    NEW = "new"
    IN_CAMPAIGN = "in_campaign"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    DEMO_REQUESTED = "demo_requested"
    CALLBACK_SCHEDULED = "callback_scheduled"
    NOT_INTERESTED = "not_interested"
    DO_NOT_CALL = "do_not_call"
    WRONG_NUMBER = "wrong_number"
    INVALID_PHONE = "invalid_phone"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class LeadPriority(StrEnum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignLeadStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    CALLING = "calling"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    SUPPRESSED = "suppressed"
    EXHAUSTED = "exhausted"


class CallStatus(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    DIALING = "dialing"
    RINGING = "ringing"
    ANSWERED = "answered"
    AGENT_ACTIVE = "agent_active"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    VOICEMAIL = "voicemail"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_CALL_STATUSES: tuple[CallStatus, ...] = (
    CallStatus.QUEUED,
    CallStatus.PREPARING,
    CallStatus.DIALING,
    CallStatus.RINGING,
    CallStatus.ANSWERED,
    CallStatus.AGENT_ACTIVE,
    CallStatus.TRANSFERRING,
)

TERMINAL_CALL_STATUSES: tuple[CallStatus, ...] = (
    CallStatus.COMPLETED,
    CallStatus.NO_ANSWER,
    CallStatus.BUSY,
    CallStatus.VOICEMAIL,
    CallStatus.REJECTED,
    CallStatus.FAILED,
    CallStatus.CANCELLED,
)

# İzin verilen durum geçişleri (state machine)
CALL_STATUS_TRANSITIONS: dict[CallStatus, frozenset[CallStatus]] = {
    CallStatus.QUEUED: frozenset({CallStatus.PREPARING, CallStatus.CANCELLED, CallStatus.FAILED}),
    CallStatus.PREPARING: frozenset(
        {CallStatus.DIALING, CallStatus.CANCELLED, CallStatus.FAILED}
    ),
    CallStatus.DIALING: frozenset(
        {
            CallStatus.RINGING,
            CallStatus.ANSWERED,
            CallStatus.NO_ANSWER,
            CallStatus.BUSY,
            CallStatus.REJECTED,
            CallStatus.VOICEMAIL,
            CallStatus.FAILED,
            CallStatus.CANCELLED,
        }
    ),
    CallStatus.RINGING: frozenset(
        {
            CallStatus.ANSWERED,
            CallStatus.NO_ANSWER,
            CallStatus.BUSY,
            CallStatus.REJECTED,
            CallStatus.VOICEMAIL,
            CallStatus.FAILED,
            CallStatus.CANCELLED,
        }
    ),
    CallStatus.ANSWERED: frozenset(
        {CallStatus.AGENT_ACTIVE, CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.VOICEMAIL}
    ),
    CallStatus.AGENT_ACTIVE: frozenset(
        {CallStatus.TRANSFERRING, CallStatus.COMPLETED, CallStatus.FAILED}
    ),
    CallStatus.TRANSFERRING: frozenset({CallStatus.COMPLETED, CallStatus.FAILED}),
}


class CallOutcome(StrEnum):
    INTERESTED = "interested"
    DEMO_REQUESTED = "demo_requested"
    CALLBACK_REQUESTED = "callback_requested"
    DECISION_MAKER_UNAVAILABLE = "decision_maker_unavailable"
    NOT_INTERESTED = "not_interested"
    DO_NOT_CALL = "do_not_call"
    WRONG_NUMBER = "wrong_number"
    BUSINESS_CLOSED = "business_closed"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    TECHNICAL_FAILURE = "technical_failure"
    TRANSFERRED_TO_HUMAN = "transferred_to_human"
    FOLLOW_UP_REQUIRED = "follow_up_required"


class ConversationEngine(StrEnum):
    OPENAI_REALTIME = "openai_realtime"
    LOCAL_PIPELINE = "local_pipeline"
    TEST = "test"


class CallbackStatus(StrEnum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    DONE = "done"
    CANCELLED = "cancelled"
    MISSED = "missed"


class DemoRequestStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class UsageSource(StrEnum):
    PROVIDER = "provider"
    ESTIMATED = "estimated"
    MIXED = "mixed"


class SuppressionSource(StrEnum):
    AGENT_CALL = "agent_call"
    MANUAL = "manual"
    IMPORT = "import"
