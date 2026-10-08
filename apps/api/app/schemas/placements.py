from datetime import datetime

from pydantic import BaseModel, Field


class PlacementIn(BaseModel):
    beneficiary_id: int
    employer: str = Field(min_length=1, max_length=200)
    role_title: str = Field(min_length=1, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=20)
    mentor_user_id: int | None = None


class PlacementStatusUpdateIn(BaseModel):
    status: str = Field(pattern="^(placed|started|graduated)$")


class PlacementOut(BaseModel):
    id: int
    beneficiary_id: int
    organization_id: int
    employer: str
    role_title: str
    skills: list[str]
    status: str
    mentor_user_id: int | None
    placed_at: datetime | None


class PlacementMatchIn(BaseModel):
    beneficiary_id: int
    limit: int = Field(default=5, ge=1, le=20)


class PlacementMatchOut(BaseModel):
    beneficiary_id: int
    skills: list[str]
    matches: list[dict]