"""Request and response models for the programs endpoints (PRD §20)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assistance import Category


class ProgramIn(BaseModel):
    organization_id: int
    name: str = Field(min_length=1, max_length=200)
    category: Category
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=100)
    budget_needed: int | None = Field(default=None, ge=0)
    is_active: bool = True


class ProgramUpdate(BaseModel):
    """All fields optional so a PATCH can touch a single attribute."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: Category | None = None
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=100)
    budget_needed: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    name: str
    category: Category
    description: str | None = None
    location: str | None = None
    budget_needed: int | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime