from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Category = Literal["food", "education", "medical", "employment", "housing", "emergency"]
Priority = Literal["critical", "high", "medium", "low"]
RequestStatus = Literal["submitted", "triaged", "approved", "fulfilled", "declined"]


class AssistanceRequestIn(BaseModel):
    # The organization whose queue handles this need. Required because an
    # assistance request must always be visible to exactly one handler set.
    organization_id: int
    description: str = Field(min_length=10, max_length=2000)


class AssistanceRequestOut(BaseModel):
    id: int
    organization_id: int
    description: str
    category: Category
    urgency_score: int = Field(ge=0, le=100)
    priority: Priority
    status: RequestStatus
    created_at: datetime


class StatusUpdateIn(BaseModel):
    status: RequestStatus
    # Free-text note kept on the audit record of the transition.
    note: str = Field(default="", max_length=500)


class PersonOut(BaseModel):
    """Linked account of a beneficiary: name and email are PII (PRD §22)."""

    id: int
    full_name: str
    email: EmailStr


class BeneficiaryOut(BaseModel):
    id: int
    organization_id: int
    household_size: int
    consented: bool
    # Non-null only when the beneficiary consented (PRD §22 consent) *and* has a
    # linked login. Everything else about them stays anonymous to the caller.
    person: PersonOut | None = None


class AssistanceRequestDetail(BaseModel):
    id: int
    description: str
    category: Category
    urgency_score: int = Field(ge=0, le=100)
    priority: Priority
    status: RequestStatus
    created_at: datetime
    beneficiary: BeneficiaryOut
