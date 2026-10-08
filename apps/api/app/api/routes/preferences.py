"""A donor's saved matching preferences (PRD Use Case 2).

Exactly one preference row per donor, always scoped by the authenticated user
id from the database: there is no path or body parameter a caller could change
to read or write another donor's preferences (the same scoping discipline as
the donation ledger).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.db.models import User
from app.db.session import get_session
from app.repositories import audit as audit_repo
from app.repositories import preferences as preferences_repo
from app.schemas.preferences import DonorPreferenceIn, DonorPreferenceOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/", response_model=DonorPreferenceOut | None)
async def get_preferences(
    session: SessionDep,
    donor: Annotated[User, Depends(require_role(Role.DONOR))],
) -> DonorPreferenceOut | None:
    """Return the caller's saved preferences, or ``null`` before the first
    PUT (the matching endpoint reports the same unset state as a 400 hint)."""
    preference = await preferences_repo.get_for_donor(session, donor.id)
    if preference is None:
        return None
    return DonorPreferenceOut.model_validate(preference)


@router.put("/", response_model=DonorPreferenceOut)
async def upsert_preferences(
    payload: DonorPreferenceIn,
    session: SessionDep,
    donor: Annotated[User, Depends(require_role(Role.DONOR))],
) -> DonorPreferenceOut:
    """Create or replace the caller's preferences. Idempotent: same body twice
    leaves the same rows (only ``updated_at`` moves)."""
    preference = await preferences_repo.upsert(
        session,
        donor_id=donor.id,
        causes=payload.causes,
        budget=payload.budget,
        location=payload.location,
    )
    await audit_repo.log_action(
        session,
        action="preferences.updated",
        entity_type="donor_preferences",
        entity_id=str(preference.id),
        organization_id=donor.organization_id,
        actor_id=donor.id,
    )
    await session.commit()
    await session.refresh(preference)
    return DonorPreferenceOut.model_validate(preference)