from dataclasses import dataclass

import httpx

from app.config import settings

_RESEND_URL = "https://api.resend.com/emails"
_TIMEOUT = 10.0


@dataclass
class EmailResult:
    sent: bool
    detail: str
    provider_id: str | None = None


def _auth_headers() -> dict[str, str]:
    if not settings.resend_api_key:
        return {"Content-Type": "application/json"}
    return {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Content-Type": "application/json",
    }


async def send_email(to: str, subject: str, body: str) -> EmailResult:
    payload = {"from": settings.email_from, "to": [to], "subject": subject, "text": body}

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            response = await client.post(
                _RESEND_URL, json=payload, headers=_auth_headers()
            )
        except (httpx.HTTPError, OSError) as exc:
            return EmailResult(sent=False, detail=f"network error: {exc}")

    if response.status_code == 200 or response.status_code == 201:
        provider_id = response.json().get("id")
        return EmailResult(sent=True, detail="accepted by Resend", provider_id=provider_id)

    return EmailResult(
        sent=False,
        detail=f"Resend returned HTTP {response.status_code}: {response.text[:200]}",
    )


async def notify_critical_request(
    recipient: str, request_id: str, description: str
) -> EmailResult:
    subject = f"[Critical] Assistance request {request_id} awaiting review"
    body = (
        "A request was classified as critical priority and needs triage.\n\n"
        f"Reference: {request_id}\n"
        f"Description: {description}\n\n"
        "Sign in to your dashboard to review and action it."
    )
    return await send_email(recipient, subject, body)
