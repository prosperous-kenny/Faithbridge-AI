
from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

from app.services.email import send_email

router = APIRouter()


class EmailTestIn(BaseModel):
    to: EmailStr
    subject: str = Field(default="FaithBridge AI test", max_length=200)
    body: str = Field(default="Testing the Resend integration.", max_length=2000)


class EmailTestOut(BaseModel):
    sent: bool
    detail: str
    provider_id: str | None = None


@router.post("/email/test", response_model=EmailTestOut)
async def test_email(payload: EmailTestIn) -> EmailTestOut:
    result = await send_email(payload.to, payload.subject, payload.body)
    return EmailTestOut(
        sent=result.sent, detail=result.detail, provider_id=result.provider_id
    )
