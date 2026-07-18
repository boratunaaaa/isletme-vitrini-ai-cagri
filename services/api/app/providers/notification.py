"""Bildirim provider'ları.

- InAppNotificationProvider: SSE üzerinden panele anlık bildirim yayınlar.
- WaMeManualNotificationProvider: WhatsApp GÖNDERMEZ; kullanıcı için manuel
  wa.me eylem linki üretir (panel 'WhatsApp aç' butonu). Meta WhatsApp API
  ileride ayrı bir adapter olarak eklenebilir.
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime

from app.providers.base import NotificationMessage
from app.services.event_bus import publish_event


class InAppNotificationProvider:
    name = "in_app"

    async def notify(self, message: NotificationMessage) -> None:
        publish_event(
            {
                "type": "notification",
                "kind": message.kind,
                "title": message.title,
                "body": message.body,
                "resource_type": message.resource_type,
                "resource_id": message.resource_id,
                "ts": (message.created_at or datetime.now(UTC)).isoformat(),
            }
        )


class WaMeManualNotificationProvider:
    """wa.me linki üretir; gönderim daima insan elindedir."""

    name = "wa_me_manual"

    @staticmethod
    def build_link(phone_e164: str, text: str) -> str:
        number = phone_e164.lstrip("+")
        return f"https://wa.me/{number}?text={urllib.parse.quote(text)}"

    async def notify(self, message: NotificationMessage) -> None:
        # Manuel kanal: bildirim yalnız uygulama içi görünür, dışarı gönderim yok.
        await InAppNotificationProvider().notify(message)
