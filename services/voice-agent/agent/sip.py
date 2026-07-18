from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from google.protobuf.duration_pb2 import Duration
from livekit import api as lk_api

from agent.config import VoiceAgentSettings
from agent.errors import SIPParticipantError, SIPTimeoutError
from agent.models import DialPlanResponse
from agent.redaction import safe_error_message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SIPParticipantHandle:
    participant_identity: str
    room_name: str
    answered: bool


class SIPParticipantAdapter(Protocol):
    async def create_participant(self, dial_plan: DialPlanResponse) -> SIPParticipantHandle: ...

    async def hangup(self, room_name: str, participant_identity: str | None = None) -> None: ...


def _http_url(livekit_url: str) -> str:
    if livekit_url.startswith("ws://"):
        return "http://" + livekit_url[len("ws://") :]
    if livekit_url.startswith("wss://"):
        return "https://" + livekit_url[len("wss://") :]
    return livekit_url


def build_sip_participant_request(
    dial_plan: DialPlanResponse,
) -> lk_api.CreateSIPParticipantRequest:
    """`CreateSIPParticipantRequest`'i saf biçimde inşa eder — ağ çağrısı
    YOKTUR (yalnız gerçek protobuf mesaj nesnesi doldurulur). Ayrı bir
    fonksiyon olarak tutulması, testlerin gerçek LiveKit sunucusuna
    bağlanmadan alan doğruluğunu doğrulayabilmesini sağlar."""
    duration = Duration()
    duration.FromSeconds(dial_plan.max_call_duration_seconds)
    return lk_api.CreateSIPParticipantRequest(
        sip_trunk_id=dial_plan.sip_trunk_id,
        sip_call_to=dial_plan.phone_e164,
        room_name=dial_plan.room_name,
        participant_identity=dial_plan.participant_identity,
        participant_name=dial_plan.participant_name,
        max_call_duration=duration,
        wait_until_answered=True,
        hide_phone_number=True,
    )


class LiveKitSIPParticipantAdapter:
    def __init__(self, settings: VoiceAgentSettings) -> None:
        self._settings = settings
        self._created: set[tuple[uuid.UUID, str]] = set()

    async def create_participant(self, dial_plan: DialPlanResponse) -> SIPParticipantHandle:
        key = (dial_plan.call_id, dial_plan.participant_identity)
        if key in self._created:
            return SIPParticipantHandle(
                participant_identity=dial_plan.participant_identity,
                room_name=dial_plan.room_name,
                answered=True,
            )
        self._created.add(key)
        request = build_sip_participant_request(dial_plan)
        try:
            return await asyncio.wait_for(
                self._create_with_client(request, dial_plan),
                timeout=self._settings.SIP_PARTICIPANT_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise SIPTimeoutError("SIP participant creation timed out.") from exc
        except lk_api.SipCallError as exc:
            # RFC 3261 SIP durum kodu korunur (busy/no_answer/rejected/... ayrımı
            # için) — yalnız redakte edilmiş mesaj değil, gerçek kod da taşınır.
            raise SIPParticipantError(
                f"SIP call failed: {safe_error_message(exc)}",
                sip_status_code=exc.sip_status_code,
                sip_status=exc.sip_status,
            ) from exc
        except Exception as exc:
            raise SIPParticipantError(f"SIP participant failed: {safe_error_message(exc)}") from exc

    async def _create_with_client(
        self,
        request: lk_api.CreateSIPParticipantRequest,
        dial_plan: DialPlanResponse,
    ) -> SIPParticipantHandle:
        client = lk_api.LiveKitAPI(
            url=_http_url(self._settings.LIVEKIT_URL),
            api_key=self._settings.LIVEKIT_API_KEY.get_secret_value(),
            api_secret=self._settings.LIVEKIT_API_SECRET.get_secret_value(),
        )
        try:
            await client.sip.create_sip_participant(request)
            return SIPParticipantHandle(
                participant_identity=dial_plan.participant_identity,
                room_name=dial_plan.room_name,
                answered=True,
            )
        finally:
            await client.aclose()

    async def hangup(self, room_name: str, participant_identity: str | None = None) -> None:
        client = lk_api.LiveKitAPI(
            url=_http_url(self._settings.LIVEKIT_URL),
            api_key=self._settings.LIVEKIT_API_KEY.get_secret_value(),
            api_secret=self._settings.LIVEKIT_API_SECRET.get_secret_value(),
        )
        try:
            if participant_identity:
                await client.room.remove_participant(
                    lk_api.RoomParticipantIdentity(
                        room=room_name,
                        identity=participant_identity,
                    )
                )
            else:
                await client.room.delete_room(lk_api.DeleteRoomRequest(room=room_name))
        except Exception as exc:
            logger.warning("LiveKit hangup failed: %s", safe_error_message(exc))
        finally:
            await client.aclose()


class FakeSIPParticipantAdapter:
    def __init__(self) -> None:
        self.created: list[DialPlanResponse] = []
        self.hangups: list[tuple[str, str | None]] = []
        self.fail: Exception | None = None
        self.answered: bool = True

    async def create_participant(self, dial_plan: DialPlanResponse) -> SIPParticipantHandle:
        if self.fail:
            raise self.fail
        if dial_plan not in self.created:
            self.created.append(dial_plan)
        return SIPParticipantHandle(
            participant_identity=dial_plan.participant_identity,
            room_name=dial_plan.room_name,
            answered=self.answered,
        )

    async def hangup(self, room_name: str, participant_identity: str | None = None) -> None:
        self.hangups.append((room_name, participant_identity))
