"""Request and response models for a donor's matching preferences."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assistance import Category


class DonorPreferenceIn(BaseModel):
    # Empty means "any cause" (the donor has no preference yet).
    causes: list[Category] = Field(default_factory=list)
    budget: float | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=100)


class DonorPreferenceOut(DonorPreferenceIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    donor_id: int
    created_at: datetime
    updated_at: datetime