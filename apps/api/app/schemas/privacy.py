"""Consent and data-deletion payloads (PRD §22)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConsentScope = Literal["beneficiary", "donor", "account"]
DeletionStatus = Literal["pending", "resolved", "rejected"]


class ConsentOut(BaseModel):
    beneficiary_id: int
    organization_id: int
    consented_at: datetime


class DeletionRequestIn(BaseModel):
    scope: ConsentScope = Field(description="What data the deletion request covers")
    reason: str | None = Field(default=None, max_length=500)


class DeletionStatusUpdateIn(BaseModel):
    status: DeletionStatus


class DeletionRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None
    requester_id: int | None
    beneficiary_id: int | None
    scope: str
    reason: str | None
    status: str
    created_at: datetime


class DeletionRequestListOut(BaseModel):
    items: list[DeletionRequestOut]
    count: int