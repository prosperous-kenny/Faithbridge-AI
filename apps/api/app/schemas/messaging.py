from datetime import datetime

from pydantic import BaseModel, Field


class WhatsAppSendIn(BaseModel):
    to_phone: str = Field(min_length=8, max_length=30)
    template: str = Field(min_length=1, max_length=50)
    variables: dict[str, str] = Field(default_factory=dict, max_length=20)


class MessageOut(BaseModel):
    id: int
    channel: str
    recipient_phone: str
    template: str
    status: str
    provider_reference: str | None
    created_at: datetime


def mask_phone(phone: str) -> str:
    """Mask everything but the last four digits for PII-safe listing."""
    if len(phone) <= 4:
        return phone
    return "*" * (len(phone) - 4) + phone[-4:]