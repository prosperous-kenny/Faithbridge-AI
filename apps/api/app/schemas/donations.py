from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DonationIn(BaseModel):
    """Create a pledge (PRD §8). ``program_id`` is the donor's stated target;
    allocation to a specific case happens later in the lifecycle."""

    organization_id: int
    amount: int = Field(gt=0, le=100_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    program_id: int | None = None


class DonationStatusUpdateIn(BaseModel):
    status: Literal["paid", "allocated", "distributed"]
    # Required when status == "allocated": allocation needs a concrete target
    # and fails otherwise (see services/donations.py allocation rules).
    beneficiary_id: int | None = None


class DonationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    donor_id: int
    organization_id: int
    program_id: int | None = None
    amount: int = Field(ge=0)
    currency: str
    status: str
    paid_at: datetime | None = None
    allocated_at: datetime | None = None
    distributed_at: datetime | None = None
    allocated_to_beneficiary_id: int | None = None
    created_at: datetime


class DonationListOut(BaseModel):
    items: list[DonationOut]
    count: int


class DonationSummaryOut(BaseModel):
    """Aggregate over a caller's ledger — never exposable to others' rows."""

    total_pledged: int
    total_paid: int
    total_allocated: int
    total_distributed: int