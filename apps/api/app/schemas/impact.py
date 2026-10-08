from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ImpactEventIn(BaseModel):
    """A recorded outcome (PRD §8 impact feed). ``organization_id`` is required
    for platform-admin writes; a faith leader is scoped to their own org."""

    organization_id: int | None = None
    metric: str = Field(min_length=1, max_length=50)
    value: int = Field(gt=0)
    occurred_at: datetime | None = None


class ImpactEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    metric: str
    value: int
    occurred_at: datetime


class ImpactEventListOut(BaseModel):
    items: list[ImpactEventOut]
    count: int


class ImpactConfigIn(BaseModel):
    weights: dict[str, float] | None = Field(default=None, description="Per-dimension weights")
    targets: dict[str, float] | None = Field(default=None, description="Per-dimension targets (value that scores 100)")


class ImpactConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    organization_id: int
    families_weight: float
    education_weight: float
    employment_weight: float
    food_security_weight: float
    healthcare_weight: float
    families_target: float
    education_target: float
    employment_target: float
    food_security_target: float
    healthcare_target: float


class ImpactComponent(BaseModel):
    value: float
    weight: float
    target: float


class ImpactScoreOut(BaseModel):
    organization_id: int
    score: int = Field(ge=0, le=100)
    components: dict[str, ImpactComponent]
    start: datetime | None = None
    end: datetime | None = None


class RollupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    period_start: datetime
    period_end: datetime
    metric: str
    total: int
    created_at: datetime


class RollupListOut(BaseModel):
    items: list[RollupOut]
    count: int


class RollupRunOut(BaseModel):
    period: str
    period_start: datetime
    period_end: datetime
    organizations: int
    totals: dict[int, dict[str, int]]