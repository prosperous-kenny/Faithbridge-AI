"""Response shapes for the donor/handler dashboard endpoints (Phase 5).

These are aggregate-only views: nothing here carries a beneficiary identity, a
case description, or an address. ``community-insights`` is intentionally a
superset of the donor Use Case 3 surface so the same PII-free contract is
asserted once, for every viewer.
"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.impact import ImpactComponent


class TrendPoint(BaseModel):
    """One calendar month: what entered the org and what left it."""

    period: str  # "YYYY-MM"
    submitted: int
    fulfilled: int
    pledged_amount: int
    paid_amount: int
    distributed_amount: int


class HighNeedCategory(BaseModel):
    category: str
    open: int
    fulfilled: int
    avg_urgency: float


class ProgramEffectiveness(BaseModel):
    program_id: int
    name: str
    pledged_amount: int
    distributed_amount: int


class DonationEffectiveness(BaseModel):
    pledged_amount: int
    paid_amount: int
    allocated_amount: int
    distributed_amount: int
    per_program: list[ProgramEffectiveness]


class CommunityInsightsOut(BaseModel):
    organization_id: int
    trends: list[TrendPoint]
    high_need_categories: list[HighNeedCategory]
    donation_effectiveness: DonationEffectiveness


class ReportMonth(BaseModel):
    """One materialised rollup row (metric total for a period)."""

    period_start: datetime
    period_end: datetime
    metric: str
    total: int


class ImpactReportOut(BaseModel):
    """The Impact Score plus the monthly breakdown behind it (PRD §15, §23)."""

    organization_id: int
    score: int
    components: dict[str, ImpactComponent]
    months: list[ReportMonth]
    period_start: datetime | None = None
    period_end: datetime | None = None