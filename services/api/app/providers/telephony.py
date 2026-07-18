"""Telephony provider implementasyonları.

LiveKitNetgsmTelephonyProvider: self-hosted LiveKit + LiveKit SIP + Netgsm
outbound trunk. Arama akışı (LiveKit resmi deseni):
  1. API explicit agent dispatch oluşturur (agent_name + metadata={call_id}).
  2. Voice agent job'ı odaya girer, dial bilgisini API'den internal endpoint
     ile alır ve CreateSIPParticipant ile numarayı arar (wait_until_answered).
Telefon numarası dispatch metadata'sına YAZILMAZ; yalnız call_id taşınır.
"""

from __future__ import annotations

import logging
from typing import Any

from livekit import api as lk_api

from app.config import get_settings
from app.providers.base import (
    OutboundCallRequest,
    TelephonyCall,
    TelephonyCallStatus,
)

logger = logging.getLogger(__name__)


class TelephonyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _http_url(livekit_url: str) -> str:
    if livekit_url.startswith("ws://"):
        return "http://" + livekit_url[len("ws://") :]
    if livekit_url.startswith("wss://"):
        return "https://" + livekit_url[len("wss://") :]
    return livekit_url


class LiveKitNetgsmTelephonyProvider:
    """LiveKit Agent Dispatch + SIP tabanlı gerçek provider."""

    name = "livekit_netgsm"

    def _client(self) -> lk_api.LiveKitAPI:
        s = get_settings()
        return lk_api.LiveKitAPI(
            url=_http_url(s.LIVEKIT_URL),
            api_key=s.LIVEKIT_API_KEY,
            api_secret=s.LIVEKIT_API_SECRET,
        )

    async def create_outbound_call(self, request: OutboundCallRequest) -> TelephonyCall:
        import json

        lkapi = self._client()
        try:
            dispatch = await lkapi.agent_dispatch.create_dispatch(
                lk_api.CreateAgentDispatchRequest(
                    agent_name=request.agent_name,
                    room=request.room_name,
                    # PII kuralı: metadata'da telefon YOK, yalnız call_id
                    metadata=json.dumps({"call_id": request.call_id}),
                )
            )
            dispatch_id = getattr(dispatch, "id", "") or request.room_name
            return TelephonyCall(provider_call_id=dispatch_id, room_name=request.room_name)
        except Exception as exc:  # SDK/ağ hataları tek tip domain hatasına çevrilir
            raise TelephonyError("dispatch_failed", f"Agent dispatch başarısız: {exc}") from exc
        finally:
            await lkapi.aclose()

    async def hangup_call(self, call_id: str) -> None:
        """call_id = LiveKit room adı. Odayı silmek SIP bacağını da düşürür."""
        lkapi = self._client()
        try:
            await lkapi.room.delete_room(lk_api.DeleteRoomRequest(room=call_id))
        except Exception as exc:
            raise TelephonyError("hangup_failed", f"Oda kapatılamadı: {exc}") from exc
        finally:
            await lkapi.aclose()

    async def transfer_call(self, call_id: str, target: str) -> None:
        """SIP REFER ile insana aktarma. call_id = room adı."""
        lkapi = self._client()
        try:
            transfer_request = lk_api.TransferSIPParticipantRequest(
                room_name=call_id,
                participant_identity=f"sip-{call_id}",
                transfer_to=f"tel:{target}",
                play_dialtone=True,
            )
            await lkapi.sip.transfer_sip_participant(transfer_request)
        except Exception as exc:
            raise TelephonyError("transfer_failed", f"Transfer başarısız: {exc}") from exc
        finally:
            await lkapi.aclose()

    async def get_call_status(self, call_id: str) -> TelephonyCallStatus:
        lkapi = self._client()
        try:
            rooms = await lkapi.room.list_rooms(lk_api.ListRoomsRequest(names=[call_id]))
            if not rooms.rooms:
                return TelephonyCallStatus(provider_call_id=call_id, state="ended")
            room = rooms.rooms[0]
            return TelephonyCallStatus(
                provider_call_id=call_id,
                state="active",
                detail=f"participants={room.num_participants}",
            )
        except Exception as exc:
            raise TelephonyError("status_failed", f"Durum okunamadı: {exc}") from exc
        finally:
            await lkapi.aclose()


class TestTelephonyProvider:
    """Otomatik testler için deterministik provider. Ağ erişimi yoktur."""

    name = "test"

    def __init__(self) -> None:
        self.created: list[OutboundCallRequest] = []
        self.hangups: list[str] = []
        self.transfers: list[tuple[str, str]] = []
        self.fail_next: str | None = None

    async def create_outbound_call(self, request: OutboundCallRequest) -> TelephonyCall:
        if self.fail_next:
            code = self.fail_next
            self.fail_next = None
            raise TelephonyError(code, "test hatası")
        self.created.append(request)
        return TelephonyCall(
            provider_call_id=f"test-{request.call_id}", room_name=request.room_name
        )

    async def hangup_call(self, call_id: str) -> None:
        self.hangups.append(call_id)

    async def transfer_call(self, call_id: str, target: str) -> None:
        self.transfers.append((call_id, target))

    async def get_call_status(self, call_id: str) -> TelephonyCallStatus:
        return TelephonyCallStatus(provider_call_id=call_id, state="active")


_test_provider = TestTelephonyProvider()


def get_telephony_provider(name: str | None = None) -> Any:
    """Provider registry. Testler `test` provider'ının aynı instance'ını görür."""
    resolved = name or "livekit_netgsm"
    if resolved == "livekit_netgsm":
        return LiveKitNetgsmTelephonyProvider()
    if resolved == "test":
        return _test_provider
    raise TelephonyError("unknown_provider", f"Bilinmeyen telephony provider: {resolved}")
