from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from livekit.agents import function_tool
from livekit.agents.llm import FunctionTool

from agent.api_client import InternalAPIClient
from agent.errors import ToolExecutionError
from agent.events import EventSink
from agent.models import AgentEventType, ToolDefinition, ToolResponse
from agent.redaction import redact_text, safe_error_message

logger = logging.getLogger(__name__)

END_CALL_TOOL_NAME = "end_call_safely"


def _base_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition(
        name="get_service_information",
        backend_path="get-service-information",
        description="İşletme Vitrini hizmetleri hakkında kontrollü bilgi al.",
        parameters=_base_schema(
            {
                "query": {"type": "string", "maxLength": 120},
                "category": {"type": "string", "maxLength": 60},
            }
        ),
    ),
    ToolDefinition(
        name="get_package_information",
        backend_path="get-package-information",
        description="Paket ve fiyat bilgisi hakkında kontrollü bilgi al.",
        parameters=_base_schema(
            {
                "query": {"type": "string", "maxLength": 120},
                "category": {"type": "string", "maxLength": 60},
            }
        ),
    ),
    ToolDefinition(
        name="request_demo_link",
        backend_path="request-demo-link",
        description="Müşteri demo bağlantısı isterse kayıt oluştur.",
        parameters=_base_schema(
            {
                "requested_channel": {
                    "type": "string",
                    "enum": ["whatsapp", "sms", "email"],
                    "default": "whatsapp",
                }
            }
        ),
    ),
    ToolDefinition(
        name="schedule_callback",
        backend_path="schedule-callback",
        description="Müşteri geri aranmak isterse callback kaydı oluştur.",
        parameters=_base_schema(
            {
                "callback_at": {"type": "string", "format": "date-time"},
                "notes": {"type": "string", "maxLength": 1000},
            },
            ["callback_at"],
        ),
    ),
    ToolDefinition(
        name="mark_interested",
        backend_path="mark-interested",
        description="Müşteri ilgilendiğinde sonucu işaretle.",
        parameters=_base_schema({"note": {"type": "string", "maxLength": 1000}}),
    ),
    ToolDefinition(
        name="mark_not_interested",
        backend_path="mark-not-interested",
        description="Müşteri ilgilenmediğinde sonucu işaretle.",
        parameters=_base_schema({"note": {"type": "string", "maxLength": 1000}}),
    ),
    ToolDefinition(
        name="mark_wrong_number",
        backend_path="mark-wrong-number",
        description="Numara yanlışsa sonucu işaretle.",
        parameters=_base_schema({"note": {"type": "string", "maxLength": 1000}}),
    ),
    ToolDefinition(
        name="mark_decision_maker_unavailable",
        backend_path="mark-decision-maker-unavailable",
        description="Yetkili kişi uygun değilse sonucu işaretle.",
        parameters=_base_schema({"note": {"type": "string", "maxLength": 1000}}),
    ),
    ToolDefinition(
        name="add_to_suppression_list",
        backend_path="add-to-suppression-list",
        description="Müşteri aranmak istemediğinde kara listeye ekle.",
        parameters=_base_schema({"reason": {"type": "string", "minLength": 2}}, ["reason"]),
    ),
    ToolDefinition(
        name="request_human_transfer",
        backend_path="request-human-transfer",
        description="Müşteri insanla görüşmek isterse aktarım talebi oluştur.",
        parameters=_base_schema({"reason": {"type": "string", "maxLength": 500}}),
    ),
    ToolDefinition(
        name="finalize_call_outcome",
        backend_path="finalize-call-outcome",
        description="Görüşme sonucunu güvenli özetle kesinleştir.",
        parameters=_base_schema(
            {
                "outcome": {"type": "string", "maxLength": 40},
                "safe_summary": {"type": "string", "maxLength": 4000},
                "interest_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "callback_at": {"type": "string", "format": "date-time"},
                "demo_requested": {"type": "boolean"},
                "transfer_requested": {"type": "boolean"},
                "notes": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
            },
            ["outcome"],
        ),
    ),
    ToolDefinition(
        name="end_call_safely",
        backend_path="end-call-safely",
        description="Görüşmeyi nazikçe kapatma niyeti bildir.",
        parameters=_base_schema({"note": {"type": "string", "maxLength": 1000}}),
    ),
)

DEFINITIONS_BY_NAME = {definition.name: definition for definition in TOOL_DEFINITIONS}


class ToolExecutor:
    def __init__(
        self,
        *,
        call_id: uuid.UUID,
        api: InternalAPIClient,
        events: EventSink,
        on_end_call_requested: Callable[[], None] | None = None,
    ) -> None:
        self._call_id = call_id
        self._api = api
        self._events = events
        self._counter = 0
        # `end_call_safely` backend'e başarıyla işlendiğinde çağrılır; job
        # handler bunu görüşmeyi kontrollü kapatma sinyali olarak kullanır
        # (bkz. agent/termination.py::CallTerminationWaiter.request_end_call).
        self._on_end_call_requested = on_end_call_requested

    def next_tool_call_id(self, tool_name: str) -> str:
        self._counter += 1
        return f"tool-{tool_name}-{self._counter}"

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        definition = DEFINITIONS_BY_NAME[tool_name]
        tool_call_id = self.next_tool_call_id(tool_name)
        payload = {
            "tool_call_id": tool_call_id,
            "occurred_at": datetime.now(UTC).isoformat(),
            **self._normalize_arguments(arguments),
        }
        try:
            # NOT (PHASE_8_RESILIENCE_REPORT.md): STARTED emit'i `important=True`
            # olduğu için kuyruğu atlayıp doğrudan `send_event` HTTP çağrısı yapar
            # — bu da başarısız olabilir. Önceden bu emit try/except DIŞINDAYDI,
            # yani kendi hatası sınıflandırılmadan (ToolExecutionError'a
            # çevrilmeden) ve FAILED event'i hiç denenmeden dışarı sızıyordu.
            await self._events.emit(
                AgentEventType.TOOL_CALL_STARTED,
                {"tool_name": tool_name, "tool_call_id": tool_call_id},
                important=True,
            )
            response = await self._api.call_tool(self._call_id, definition.backend_path, payload)
        except Exception as exc:
            try:
                await self._events.emit(
                    AgentEventType.TOOL_CALL_FAILED,
                    {"tool_name": tool_name, "tool_call_id": tool_call_id},
                    important=True,
                )
            except Exception:
                # FAILED event'in kendisi de başarısız olabilir (ör. backend
                # tamamen erişilemez) — bu, asıl hatayı maskelememeli.
                logger.warning(
                    "tool_call_failed_event_emit_failed",
                    extra={"tool_name": tool_name, "tool_call_id": tool_call_id},
                )
            raise ToolExecutionError(f"Tool failed: {safe_error_message(exc)}") from exc
        await self._events.emit(
            AgentEventType.TOOL_CALL_COMPLETED,
            {"tool_name": tool_name, "tool_call_id": tool_call_id},
            important=True,
        )
        if tool_name == END_CALL_TOOL_NAME and self._on_end_call_requested is not None:
            self._on_end_call_requested()
        return summarize_tool_result(tool_name, response)

    @staticmethod
    def _normalize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in arguments.items() if value is not None}


def summarize_tool_result(tool_name: str, response: ToolResponse) -> str:
    result = response.result
    if tool_name in {"get_service_information", "get_package_information"}:
        count = len(result.get("items", [])) if isinstance(result.get("items"), list) else 0
        return f"Bilgi bankasından {count} kayıt alındı. Yanıtı kısa ve doğal aktar."
    if tool_name == "request_demo_link":
        return "Demo talebi kaydedildi. Müşteriye demo bağlantısının iletileceğini söyle."
    if tool_name == "schedule_callback":
        return "Geri arama kaydedildi. Saati kısa ve net şekilde teyit et."
    if tool_name == "request_human_transfer":
        if result.get("transfer_available"):
            return "İnsan temsilci aktarım talebi uygun. Müşteriye kısa bekleme bilgisi ver."
        return "İnsan temsilci aktarımı şu anda uygun değil. Görüşmeyi nazikçe sürdür."
    if tool_name == "end_call_safely":
        return "Görüşmeyi kısa bir teşekkürle kapat. Yeni soru sorma."
    if tool_name == "finalize_call_outcome":
        return "Görüşme sonucu kaydedildi. Müşteriye ham sistem sonucu okuma."
    outcome = result.get("outcome")
    if outcome:
        return f"Sonuç {redact_text(str(outcome))} olarak kaydedildi. Doğal konuşmaya devam et."
    return "İşlem kaydedildi. Ham sistem çıktısını müşteriye okuma."


class ToolRegistry:
    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return TOOL_DEFINITIONS

    def livekit_tools(self) -> list[FunctionTool]:
        executor = self._executor

        @function_tool(name="get_service_information")
        async def get_service_information(
            query: str | None = None,
            category: str | None = None,
        ) -> str:
            return await executor.execute(
                "get_service_information", {"query": query, "category": category}
            )

        @function_tool(name="get_package_information")
        async def get_package_information(
            query: str | None = None,
            category: str | None = None,
        ) -> str:
            return await executor.execute(
                "get_package_information", {"query": query, "category": category}
            )

        @function_tool(name="request_demo_link")
        async def request_demo_link(requested_channel: str = "whatsapp") -> str:
            return await executor.execute(
                "request_demo_link",
                {"requested_channel": requested_channel},
            )

        @function_tool(name="schedule_callback")
        async def schedule_callback(callback_at: str, notes: str | None = None) -> str:
            return await executor.execute(
                "schedule_callback", {"callback_at": callback_at, "notes": notes}
            )

        @function_tool(name="mark_interested")
        async def mark_interested(note: str | None = None) -> str:
            return await executor.execute("mark_interested", {"note": note})

        @function_tool(name="mark_not_interested")
        async def mark_not_interested(note: str | None = None) -> str:
            return await executor.execute("mark_not_interested", {"note": note})

        @function_tool(name="mark_wrong_number")
        async def mark_wrong_number(note: str | None = None) -> str:
            return await executor.execute("mark_wrong_number", {"note": note})

        @function_tool(name="mark_decision_maker_unavailable")
        async def mark_decision_maker_unavailable(note: str | None = None) -> str:
            return await executor.execute("mark_decision_maker_unavailable", {"note": note})

        @function_tool(name="add_to_suppression_list")
        async def add_to_suppression_list(reason: str) -> str:
            return await executor.execute("add_to_suppression_list", {"reason": reason})

        @function_tool(name="request_human_transfer")
        async def request_human_transfer(reason: str | None = None) -> str:
            return await executor.execute("request_human_transfer", {"reason": reason})

        @function_tool(name="finalize_call_outcome")
        async def finalize_call_outcome(
            outcome: str,
            safe_summary: str | None = None,
            interest_level: str | None = None,
            callback_at: str | None = None,
            demo_requested: bool = False,
            transfer_requested: bool = False,
        ) -> str:
            return await executor.execute(
                "finalize_call_outcome",
                {
                    "outcome": outcome,
                    "safe_summary": safe_summary,
                    "interest_level": interest_level,
                    "callback_at": callback_at,
                    "demo_requested": demo_requested,
                    "transfer_requested": transfer_requested,
                    "notes": [],
                },
            )

        @function_tool(name="end_call_safely")
        async def end_call_safely(note: str | None = None) -> str:
            return await executor.execute("end_call_safely", {"note": note})

        return [
            get_service_information,
            get_package_information,
            request_demo_link,
            schedule_callback,
            mark_interested,
            mark_not_interested,
            mark_wrong_number,
            mark_decision_maker_unavailable,
            add_to_suppression_list,
            request_human_transfer,
            finalize_call_outcome,
            end_call_safely,
        ]
