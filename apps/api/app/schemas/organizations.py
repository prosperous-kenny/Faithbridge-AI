"""Request and response models for the organizations endpoints (PRD §11)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.repositories.organizations import ORG_TYPES


class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    org_type: str = Field(default="church", max_length=50)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        # Whitespace is not a name: "   " would otherwise create an
        # unidentifiable tenant once it is trimmed in the browser.
        name = value.strip()
        if not name:
            raise ValueError("name must not be blank")
        return name

    @field_validator("org_type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in ORG_TYPES:
            raise ValueError(f"org_type must be one of {', '.join(ORG_TYPES)}")
        return value


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    org_type: str
    created_at: datetime
    updated_at: datetime
