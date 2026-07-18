from __future__ import annotations

import uuid
from datetime import UTC, datetime

from agent.models import (
    AgentConfiguration,
    BootstrapCampaign,
    BootstrapLead,
    BootstrapResponse,
    DialPlanResponse,
    PolicyContext,
    TelephonyContext,
)


def bootstrap() -> BootstrapResponse:
    return BootstrapResponse(
        call_id=uuid.uuid4(),
        lead=BootstrapLead(
            business_name="Örnek İşletme",
            sector="Güzellik",
            city="İstanbul",
            district="Kadıköy",
            website="https://example.invalid",
            phone_e164="+905551112233",
            phone_last_four="2233",
        ),
        campaign=BootstrapCampaign(
            campaign_id=uuid.uuid4(),
            name="Test Kampanya",
            conversation_engine="openai_realtime",
            model="gpt-realtime-2.1-mini",
            voice="marin",
            max_call_duration_seconds=300,
        ),
        agent_configuration=AgentConfiguration(
            prompt_version_id=uuid.uuid4(),
            system_prompt="Sistem promptu",
            opening_script="Merhaba, İşletme Vitrini adına arıyorum.",
            objective="Demo ilgisini ölç.",
            objection_rules="Bilmediğini uydurma.",
            tool_policy={"controlled_tools_only": True},
        ),
        knowledge_base=[],
        telephony=TelephonyContext(
            outbound_trunk_id="trunk",
            caller_id="+902161110000",
            sip_transport="udp",
            codec_preferences=[],
        ),
        policy=PolicyContext(
            recording_enabled=False,
            transcript_storage_enabled=True,
            human_transfer_enabled=False,
        ),
    )


def dial_plan(
    call_id: uuid.UUID | None = None, *, max_call_duration_seconds: int = 300
) -> DialPlanResponse:
    return DialPlanResponse(
        call_id=call_id or uuid.uuid4(),
        phone_e164="+905551112233",
        sip_trunk_id="trunk",
        caller_id="+902161110000",
        room_name="call-room",
        participant_identity="phone-123",
        participant_name="Örnek İşletme",
        max_call_duration_seconds=max_call_duration_seconds,
    )


def now() -> datetime:
    return datetime.now(UTC)
