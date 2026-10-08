"""Messaging provider interface: WhatsApp first (PRD §14).

The ``MockMessagingProvider`` records deliveries in memory and returns a
deterministic reference so the message table and audit trail are populated
exactly as with a real backend. The Twilio adapter is constructed only when
credentials exist; an unset credential is a loud configuration error because a
message "sent" to nowhere would erode the trust the trail exists to protect.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.config import settings


class MessagingError(RuntimeError):
    """The provider rejected the message (mapped to 502 by routes)."""


@dataclass(frozen=True)
class SendResult:
    """The provider's acknowledgment of one message."""

    ok: bool
    provider_reference: str | None = None
    detail: str = ""


@runtime_checkable
class MessagingProvider(Protocol):
    """Sends templated messages through a channel adapter."""

    name: str
    channel: str

    async def send(
        self, *, to_phone: str, template: str, variables: dict[str, str]
    ) -> SendResult:
        """Deliver a message; raise MessagingError on a hard failure."""
        ...


class MockMessagingProvider:
    """Deterministic in-process adapter. Nothing leaves the process."""

    name = "mock"
    channel = "whatsapp"

    async def send(
        self, *, to_phone: str, template: str, variables: dict[str, str]
    ) -> SendResult:
        return SendResult(
            ok=True,
            provider_reference=f"mock_msg_{secrets.token_hex(8)}",
            detail=f"{template} -> {to_phone}",
        )


class TwilioWhatsAppProvider:
    """Twilio WhatsApp adapter. Requires Twilio credentials; raises otherwise."""

    name = "twilio"
    channel = "whatsapp"

    def __init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("TWILIO_ACCOUNT_SID", settings.twilio_account_sid),
                ("TWILIO_AUTH_TOKEN", settings.twilio_auth_token),
            )
            if not value
        ]
        if missing:
            raise MessagingError("Twilio WhatsApp requires " + ", ".join(missing))
        self._from = settings.twilio_whatsapp_from

    async def send(
        self, *, to_phone: str, template: str, variables: dict[str, str]
    ) -> SendResult:
        try:
            from twilio.rest import Client  # type: ignore[import-not-found]

            phone = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
            body = f"{template}: " + ", ".join(variables.values())
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            message = client.messages.create(from_=self._from, to=phone, body=body)
            return SendResult(ok=True, provider_reference=message.sid)
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise MessagingError("twilio package is not installed") from exc


_provider: MessagingProvider | None = None


def get_messaging_provider() -> MessagingProvider:
    """Cache the configured provider for the process lifetime."""
    global _provider
    if _provider is None:
        if settings.whatsapp_provider == "twilio":
            _provider = TwilioWhatsAppProvider()
        elif settings.whatsapp_provider == "mock":
            _provider = MockMessagingProvider()
        else:
            raise MessagingError(
                f"WHATSAPP_PROVIDER={settings.whatsapp_provider!r} is not mock or twilio"
            )
    return _provider