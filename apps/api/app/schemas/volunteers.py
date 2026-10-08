from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.volunteering import AVAILABILITY_SLOTS


class VolunteerIn(BaseModel):
    """Create or update the caller's own volunteer profile.

    ``organization_id`` defaults to the caller's own organization in the
    route; it exists only so a platform admin can register a volunteer for
    an organization they do not belong to.
    """

    organization_id: int | None = None
    skills: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Skill names, each at most 50 characters",
    )
    availability: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("skills")
    @classmethod
    def _clean_skills(cls, skills: list[str]) -> list[str]:
        cleaned = [skill.strip() for skill in skills]
        if any(not skill or len(skill) > 50 for skill in cleaned):
            raise ValueError("skills must be non-empty strings of at most 50 characters")
        return cleaned

    @field_validator("availability")
    @classmethod
    def _valid_slots(cls, slots: list[str]) -> list[str]:
        unknown = [slot for slot in slots if slot not in AVAILABILITY_SLOTS]
        if unknown:
            raise ValueError(
                f"unknown availability slots {unknown!r}; allowed: "
                f"{sorted(AVAILABILITY_SLOTS)}"
            )
        return slots


class VolunteerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    user_id: int
    skills: list[str]
    availability: list[str]
    is_active: bool
    created_at: datetime


class VolunteerMatchIn(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=20)
    availability: list[str] = Field(default_factory=list, max_length=6)
    organization_id: int | None = None
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("availability")
    @classmethod
    def _valid_slots(cls, slots: list[str]) -> list[str]:
        unknown = [slot for slot in slots if slot not in AVAILABILITY_SLOTS]
        if unknown:
            raise ValueError(f"unknown availability slots {unknown!r}")
        return slots


class VolunteerMatchOut(BaseModel):
    organization_id: int
    skills: list[str]
    availability: list[str]
    matches: list[dict]
