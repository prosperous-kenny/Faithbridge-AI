"""Request and response models for `POST /ai/match-donors` (PRD §21).

The request carries optional inline overrides; anything omitted falls back to
the donor's saved preferences (PRD Use Case 2). The response is the ranked,
PII-free program list a donor sees.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.assistance import Category


class MatchRequest(BaseModel):
    causes: list[Category] | None = None
    budget: float | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=100)


class MatchItem(BaseModel):
    program_id: int
    program_name: str
    organization_name: str
    category: Category
    location: str | None = None
    budget_needed: int | None = None
    # Consent-clean count of open assistance cases this program's org carries
    # for its category (PRD §22: never a beneficiary identity).
    open_cases: int = Field(ge=0)
    match_score: float = Field(ge=0, le=1)
    matches_causes: bool
    matches_budget: bool
    matches_location: bool
    reason: str


class MatchResponse(BaseModel):
    engine: str
    matches: list[MatchItem]